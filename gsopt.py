
import pandas as pd
from flask import Flask, request, jsonify
import numpy as np
from skopt import Optimizer
from skopt.space import Real

app = Flask(__name__)
SPREADSHEET_FILE = "gsopt_cache.csv"
DIMENSIONS = 2
BATCH_SIZE = 10

def get_cache_as_dataframe():
    """Reads the cache file and returns a pandas DataFrame."""
    try:
        df = pd.read_csv(SPREADSHEET_FILE)
        df['result'] = pd.to_numeric(df['result'], errors='coerce')
        return df
    except Exception as e:  
        headers = [f'x{i+1}' for i in range(DIMENSIONS)] + ['result']
        return pd.DataFrame(columns=headers)


def write_to_cache(df):
    """Writes the DataFrame back to the cache file."""
    df.to_csv(SPREADSHEET_FILE, index=False)

def rosenbrock(x):
    """The Rosenbrock function for 2 dimensions."""
    return (1.0 - x[0])**2 + 100.0 * (x[1] - x[0]**2)**2

def build_and_train_optimizer(dimensions, base_estimator, acq_func):
    """
    Builds a new optimizer and trains it with all data from the spreadsheet.
    This makes the function completely stateless.
    """
    
    # Define the search space
    space = []
    for k,v in dimensions.items():
        space.append(Real(v[0], v[1], name=k))

    print(space)
    # Initialize the optimizer
    optimizer = Optimizer(space, base_estimator=base_estimator, acq_func=acq_func)
    
    # Read all the data from the cache
    df_cache = get_cache_as_dataframe()
    evaluated_points = df_cache[df_cache['result'].notnull()]
    
    # If there is data, train the optimizer with it
    if not evaluated_points.empty:
        x_train = evaluated_points[[f'x{i+1}' for i in range(DIMENSIONS)]].values
        y_train = evaluated_points['result'].values
        optimizer.tell(x_train.tolist(), y_train.tolist())
    print('foo')
    return optimizer

# this request should contain dimenions, base_estimator, acq_func
@app.route('/start-optimization', methods=['POST'])
def start_optimization():
    data = request.get_json()
    dimensions = data.get('dimensions')
    base_estimator:str = data.get('base_estimator', 'GP')
    acq_func:str = data.get('acq_func', 'EI')
    batch_size:int = data.get('batch_size')

    # Build a fresh optimizer and get the initial points
    optimizer = build_and_train_optimizer(dimensions, base_estimator, acq_func)
    initial_points = optimizer.ask(n_points=batch_size)
    
    # Update the cache with these new points
    headers = [f'x{i+1}' for i in range(len(dimensions))] + ['result']
    df = pd.DataFrame(initial_points, columns=headers[:-1])
    df['result'] = np.nan
    write_to_cache(df)

    return jsonify({
        "message": f"Optimization started. {len(df)} initial points have been added to the spreadsheet for evaluation."
    })

@app.route('/simulate-user-input', methods=['POST'])
def simulate_user_input():
    df_cache = get_cache_as_dataframe()
    pending_points = df_cache[df_cache['result'].isnull()]
    
    for index, row in pending_points.iterrows():
        x_values = row[[f'x{i+1}' for i in range(DIMENSIONS)]].values
        result = rosenbrock(x_values)
        df_cache.loc[index, 'result'] = result

    write_to_cache(df_cache)
    
    return jsonify({
        "message": f"Simulated user input. {len(pending_points)} points have been evaluated and the cache is updated."
    })

@app.route('/continue-optimization', methods=['POST'])
def continue_optimization():
    data = request.get_json()
    dimensions = data.get('dimensions')
    base_estimator:str = data.get('base_estimator', 'GP')
    acq_func:str = data.get('acq_func', 'EI')
    batch_size:int = data.get('batch_size', BATCH_SIZE)

    # Build a fresh optimizer and train it with all the existing data
    optimizer = build_and_train_optimizer(dimensions, base_estimator, acq_func)
    
    # Ask the optimizer for a new batch of points
    new_points = optimizer.ask(n_points=BATCH_SIZE)
    
    # Get the current cache, add the new points, and write it back
    df_cache = get_cache_as_dataframe()
    headers = [f'x{i+1}' for i in range(DIMENSIONS)] + ['result']
    df_new = pd.DataFrame(new_points, columns=headers[:-1])
    df_new['result'] = np.nan
    df_updated_cache = pd.concat([df_cache, df_new], ignore_index=True)
    write_to_cache(df_updated_cache)
    
    return jsonify({
        "message": f"Optimization state updated. A new batch of {len(new_points)} points is ready for evaluation.",
        "points_to_evaluate": new_points
    })

if __name__ == '__main__':
    df = get_cache_as_dataframe()
    if df.empty:
        df = pd.DataFrame(columns=[f'x{i+1}' for i in range(DIMENSIONS)] + ['result'])
        df.to_csv(SPREADSHEET_FILE, index=False)
        print("Initial cache file created. Run /start-optimization to populate it.")

    app.run(host='0.0.0.0', port=8080, debug=True)