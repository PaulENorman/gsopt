import pandas as pd
from dataclasses import dataclass
from flask import Flask, request, jsonify
import numpy as np
from skopt import Optimizer
from skopt.space import Real
from google.oauth2 import service_account
from googleapiclient.discovery import build
from typing import Dict, List, Any, Optional, Tuple
import logging
import google.auth

# Configure logging with timestamp and log level
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@dataclass
class OptimizerSettings:
    """Configuration settings for the Bayesian optimizer."""
    base_estimator: str
    acquisition_function: str
    num_params: int
    param_names: List[str]
    param_mins: List[float]
    param_maxes: List[float]
    num_init_points: int
    batch_size: int

# Google Sheets API configuration
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Initialize Google Sheets API client
# The client will automatically find credentials from the environment when running on GCP.
creds, project = google.auth.default(scopes=SCOPES)
service = build('sheets', 'v4', credentials=creds)
sheet = service.spreadsheets()

def get_optimizer_settings(sheet, spreadsheet_id: str, sheet_name: str) -> OptimizerSettings:
    """
    Reads optimizer configuration from the specified Optimizer Settings sheet.
    
    Expected sheet layout:
        B2: Base estimator (e.g., "Gaussian Process (GP)")
        B3: Acquisition function (e.g., "Expected Improvement (EI)")
        B4: Number of initial points
        B5: Batch size
        B7: Number of parameters
        A9:A: Parameter names
        B9:B: Parameter minimums
        C9:C: Parameter maximums
    
    Args:
        sheet: Google Sheets API resource
        spreadsheet_id: ID of the spreadsheet containing optimizer settings
        sheet_name: Name of the sheet containing optimizer settings
        
    Returns:
        OptimizerSettings dataclass with parsed configuration
    """
    def _fetch(range_a1: str) -> List[List[Any]]:
        """Fetch values from a sheet range."""
        result = sheet.values().get(spreadsheetId=spreadsheet_id, range=range_a1).execute()
        return result.get('values', []) or []

    def _first_cell(range_a1: str) -> Optional[str]:
        """Extract the first cell value from a range."""
        vals = _fetch(range_a1)
        if not vals:
            return None
        row0 = vals[0] if isinstance(vals[0], list) else [vals[0]]
        return row0[0] if row0 else None

    def _col(range_a1: str) -> List[str]:
        """Extract a column of values as strings."""
        vals = _fetch(range_a1)
        out = []
        for r in vals:
            if isinstance(r, list) and r:
                out.append(str(r[0]))
            elif isinstance(r, str):
                out.append(r)
            else:
                out.append("")
        return out

    def _parse_parens(s: Optional[str]) -> Optional[str]:
        """Extract text within parentheses, e.g., 'Gaussian Process (GP)' -> 'GP'."""
        if not s:
            return None
        s = str(s)
        l = s.find("(")
        if l == -1:
            return s.strip()
        r = s.find(")", l + 1)
        if r == -1:
            return s.strip()
        return s[l+1:r].strip()

    # Read configuration cells
    base_estimator_raw = _first_cell(f"{sheet_name}!B2")
    acquisition_raw = _first_cell(f"{sheet_name}!B3")
    num_params_raw = _first_cell(f"{sheet_name}!B7")
    num_init_points_raw = _first_cell(f"{sheet_name}!B4")
    batch_size_raw = _first_cell(f"{sheet_name}!B5")

    # Parse string values
    base_estimator = _parse_parens(base_estimator_raw)
    acquisition_function = _parse_parens(acquisition_raw)

    # Parse integer values with error handling
    try:
        num_params = int(str(num_params_raw).strip()) if num_params_raw is not None else 0
    except ValueError:
        num_params = 0

    try:
        num_init_points = int(str(num_init_points_raw).strip()) if num_init_points_raw is not None else 0
    except ValueError:
        num_init_points = 0

    try:
        batch_size = int(str(batch_size_raw).strip()) if batch_size_raw is not None else 0
    except ValueError:
        batch_size = 0

    # Read parameter specifications
    names_col = [n for n in _col(f"{sheet_name}!A9:A") if n != ""]
    mins_col = [m for m in _col(f"{sheet_name}!B9:B") if m != ""]
    maxes_col = [x for x in _col(f"{sheet_name}!C9:C") if x != ""]

    def _pad(lst: List[str], n: int, pad_val: str = "") -> List[str]:
        """Pad or truncate list to specified length."""
        return lst + [pad_val] * (n - len(lst)) if len(lst) < n else lst[:n]

    names = [(n.strip() if n is not None else "") for n in _pad(names_col, num_params)]
    param_mins_str = [(m.strip() if m is not None else "") for m in _pad(mins_col, num_params)]
    param_maxes_str = [(x.strip() if x is not None else "") for x in _pad(maxes_col, num_params)]

    def _to_float(v: str) -> float:
        """Convert string to float with fallback to 0.0."""
        try:
            if v is None or v == "":
                return 0.0
            return float(v)
        except (ValueError, TypeError):
            return 0.0

    param_mins = [_to_float(v) for v in param_mins_str]
    param_maxes = [_to_float(v) for v in param_maxes_str]

    return OptimizerSettings(
        base_estimator=base_estimator,
        acquisition_function=acquisition_function,
        num_params=num_params,
        param_names=names,
        param_mins=param_mins,
        param_maxes=param_maxes,
        num_init_points=num_init_points,
        batch_size=batch_size
    )

def get_data_from_sheet(sheet, spreadsheet_id: str, sheet_name: str, num_params: int) -> pd.DataFrame:
    """
    Reads optimization data from the specified Data sheet.
    
    Expected layout:
        Row 3: Headers (parameter names + objective column)
        Row 4+: Data rows
        
    Args:
        sheet: Google Sheets API resource
        spreadsheet_id: ID of the spreadsheet containing the data
        sheet_name: Name of the data sheet
        num_params: Number of parameter columns to read
        
    Returns:
        DataFrame with parameter columns and one objective column
    """
    def _fetch(range_a1: str) -> List[List[Any]]:
        # Use the passed-in spreadsheet_id
        result = sheet.values().get(spreadsheetId=spreadsheet_id, range=range_a1).execute()
        return result.get('values', []) or []
    
    # Fetch data starting from row 3 (headers)
    data_range = f"{sheet_name}!A3:ZZ"
    values = _fetch(data_range)
    
    if not values or len(values) < 1:
        return pd.DataFrame()
    
    headers = values[0]
    data_rows = values[1:] if len(values) > 1 else []
    
    if not data_rows:
        return pd.DataFrame(columns=headers)
    
    # Extract only parameter columns + objective column
    headers_subset = headers[:num_params + 1]
    data_rows_subset = [row[:num_params + 1] for row in data_rows]
    
    df = pd.DataFrame(data_rows_subset, columns=headers_subset)
    
    return df

def build_and_train_optimizer(
    dimensions: Dict[str, Tuple[float, float]], 
    base_estimator: str, 
    acq_func: str, 
    num_params: int,
    spreadsheet_id: str  # Pass spreadsheet_id here
) -> Optimizer:
    """
    Creates and trains a Bayesian optimizer with existing data from a specific sheet.
    
    Args:
        dimensions: Dict mapping parameter names to (min, max) tuples
        base_estimator: Type of surrogate model (e.g., 'GP', 'ET', 'RF')
        acq_func: Acquisition function (e.g., 'EI', 'PI', 'LCB')
        num_params: Number of optimization parameters
        spreadsheet_id: ID of the spreadsheet containing the data
        
    Returns:
        Trained Optimizer instance
    """
    # Define search space
    space = [Real(v[0], v[1], name=k) for k, v in dimensions.items()]
    logger.info(f"Created search space with {len(space)} dimensions")

    # Initialize optimizer with performance settings
    optimizer = Optimizer(
        space, 
        base_estimator=base_estimator, 
        acq_func=acq_func,
        n_initial_points=5  # Reduced random exploration for faster convergence
    )
    logger.info(f"Initialized optimizer with base_estimator={base_estimator}, acq_func={acq_func}")
    
    # Load existing data from the specified sheet
    df_data = get_data_from_sheet(sheet, spreadsheet_id, "Data", num_params)
    logger.info(f"Retrieved data from sheet {spreadsheet_id}: shape={df_data.shape}")
    
    if not df_data.empty and len(df_data.columns) > num_params:
        objective_col = df_data.columns[num_params]
        logger.info(f"Objective column: {objective_col}")
        
        # Clean and prepare data
        df_data_clean = df_data.copy()
        df_data_clean[objective_col] = df_data_clean[objective_col].replace('', np.nan)
        df_data_clean[objective_col] = pd.to_numeric(df_data_clean[objective_col], errors='coerce')
        
        # Filter to evaluated points only
        evaluated_points = df_data_clean[df_data_clean[objective_col].notnull()]
        logger.info(f"Found {len(evaluated_points)} evaluated points")
        
        if not evaluated_points.empty:
            param_cols = df_data.columns[:num_params].tolist()
            
            x_train = evaluated_points[param_cols].values
            y_train = evaluated_points[objective_col].values
            
            # Convert parameters to numeric, handling empty strings
            x_train_numeric = []
            for row in x_train:
                numeric_row = [float(val) if val != '' else 0.0 for val in row]
                x_train_numeric.append(numeric_row)
            
            # Train optimizer with all evaluated data
            optimizer.tell(x_train_numeric, y_train.tolist())
            logger.info(f"Successfully trained optimizer with {len(x_train_numeric)} points")
        else:
            logger.warning("No evaluated points found to train optimizer")
    else:
        logger.warning("No data found in sheet or insufficient columns")
    
    return optimizer

def write_data_to_sheet(sheet, spreadsheet_id: str, data_df: pd.DataFrame, sheet_name: str = "Data") -> None:
    """
    Writes data to the specified Data sheet starting at row 4.
    
    Overwrites any existing data. Headers in row 3 are assumed to be pre-populated.
    
    Args:
        sheet: Google Sheets API resource
        spreadsheet_id: ID of the spreadsheet to write to
        data_df: DataFrame to write (without headers)
        sheet_name: Name of the target sheet
    """
    data_df = data_df.fillna('')
    values = data_df.values.tolist()
    
    range_name = f"{sheet_name}!A4"
    body = {'values': values}
    
    sheet.values().update(
        spreadsheetId=spreadsheet_id,  # Use the passed-in spreadsheet_id
        range=range_name,
        valueInputOption='RAW',
        body=body
    ).execute()

def append_data_to_sheet(sheet, spreadsheet_id: str, data_df: pd.DataFrame, sheet_name: str = "Data") -> None:
    """
    Appends data to the specified Data sheet at the next available row.
    
    Args:
        sheet: Google Sheets API resource
        spreadsheet_id: ID of the spreadsheet to append to
        data_df: DataFrame to append (without headers)
        sheet_name: Name of the target sheet
    """
    def _fetch(range_a1: str) -> List[List[Any]]:
        result = sheet.values().get(spreadsheetId=spreadsheet_id, range=range_a1).execute()
        return result.get('values', []) or []
    
    # Find next empty row
    data_range = f"{sheet_name}!A4:A"
    existing = _fetch(data_range)
    next_row = 4 + len(existing)
    
    data_df = data_df.fillna('')
    values = data_df.values.tolist()
    
    range_name = f"{sheet_name}!A{next_row}"
    body = {'values': values}
    
    sheet.values().update(
        spreadsheetId=spreadsheet_id, # Use the passed-in spreadsheet_id
        range=range_name,
        valueInputOption='RAW',
        body=body
    ).execute()

@app.route('/init-optimization', methods=['POST'])
def init_optimization():
    """
    Initialize optimization for a specific spreadsheet.
    
    Returns:
        JSON response with status and message
    """
    try:
        data = request.get_json()
        spreadsheet_id = data.get('spreadsheet_id')
        if not spreadsheet_id:
            return jsonify({"status": "error", "message": "spreadsheet_id is required"}), 400

        logger.info(f"Starting optimization initialization for sheet: {spreadsheet_id}")
        
        optimizer_settings = get_optimizer_settings(sheet, spreadsheet_id, "Optimizer Settings")
        
        dimensions = {
            name: (optimizer_settings.param_mins[i], optimizer_settings.param_maxes[i])
            for i, name in enumerate(optimizer_settings.param_names)
        }
        
        optimizer = build_and_train_optimizer(
            dimensions,
            optimizer_settings.base_estimator,
            optimizer_settings.acquisition_function,
            optimizer_settings.num_params,
            spreadsheet_id  # Pass the ID through
        )
        
        # Generate initial points
        initial_points = optimizer.ask(n_points=optimizer_settings.num_init_points)
        logger.info(f"Generated {len(initial_points)} initial points")
        
        # Write to sheet with empty objective column
        df = pd.DataFrame(initial_points, columns=optimizer_settings.param_names)
        df['object'] = ''
        
        write_data_to_sheet(sheet, spreadsheet_id, df)
        logger.info(f"Successfully wrote initial points to sheet: {spreadsheet_id}")

        return jsonify({"status": "success", "message": "Optimization initialized successfully"})
    except Exception as e:
        logger.error(f"Failed to initialize optimization: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to initialize optimization"}), 500

@app.route('/continue-optimization', methods=['POST'])
def continue_optimization():
    """
    Continue optimization for a specific spreadsheet.
    
    Returns:
        JSON response with status and message
    """
    try:
        data = request.get_json()
        spreadsheet_id = data.get('spreadsheet_id')
        if not spreadsheet_id:
            return jsonify({"status": "error", "message": "spreadsheet_id is required"}), 400

        logger.info(f"Continuing optimization for sheet: {spreadsheet_id}")
        
        optimizer_settings = get_optimizer_settings(sheet, spreadsheet_id, "Optimizer Settings")

        dimensions = {
            name: (optimizer_settings.param_mins[i], optimizer_settings.param_maxes[i])
            for i, name in enumerate(optimizer_settings.param_names)
        }
        
        optimizer = build_and_train_optimizer(
            dimensions,
            optimizer_settings.base_estimator,
            optimizer_settings.acquisition_function,
            optimizer_settings.num_params,
            spreadsheet_id # Pass the ID through
        )
        
        # Generate new batch of points
        new_points = optimizer.ask(n_points=optimizer_settings.batch_size)
        logger.info(f"Generated {len(new_points)} new points")
        
        # Append to sheet with empty objective column
        df_new = pd.DataFrame(new_points, columns=optimizer_settings.param_names)
        df_new['object'] = ''
        
        append_data_to_sheet(sheet, spreadsheet_id, df_new)
        logger.info(f"Successfully appended new points to sheet: {spreadsheet_id}")
        
        return jsonify({"status": "success", "message": "Optimization continued successfully"})
    except Exception as e:
        logger.error(f"Failed to continue optimization: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to continue optimization"}), 500

if __name__ == '__main__':
    # The app no longer loads settings on startup, as it needs a spreadsheet_id first.
    app.run(host='0.0.0.0', port=8080, debug=False)