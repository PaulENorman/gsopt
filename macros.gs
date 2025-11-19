// Replace this with the URL of your deployed Cloud Run service.
const CLOUD_RUN_URL = 'https://gsopt-449559265504.europe-west1.run.app'; 

/**
 * Adds a custom menu to the spreadsheet when it's opened.
 */
function onOpen() {
  SpreadsheetApp.getUi()
      .createMenu('Optimizer')
      .addItem('1. Initialize Optimization', 'initOptimization')
      .addItem('2. Continue Optimization', 'continueOptimization')
      .addSeparator()
      .addItem('Test Connection', 'testCloudRunConnection')
      .addToUi();
}

/**
 * Trigger function that runs automatically whenever an edit occurs in the spreadsheet.
 * It checks if the edit happened in the target cell (B7 on "Optimizer Settings") 
 * and generates the parameter rows.
 * @param {GoogleAppsScript.Events.SheetsOnEdit} e The edit event object.
 */
function onEdit(e) {
  // Define the target location for the trigger
  const TARGET_SHEET_NAME = "Optimizer Settings";
  const TARGET_CELL_A1 = "B7"; 

  // Exit immediately if the event object is missing or if the edited range is not a single cell
  if (!e || !e.range) return;
  
  const sheet = e.range.getSheet();
  const editedRange = e.range;

  // 1. Check if the edited cell is the target cell in the target sheet
  if (sheet.getName() === TARGET_SHEET_NAME && editedRange.getA1Notation() === TARGET_CELL_A1) {
    // 2. Call the function that generates the parameter rows
    try {
      generateParameterRanges(sheet);
    } catch (error) {
      // In a clean version, we only log errors for silent failure monitoring
      // (The user won't see this unless they check the Apps Script logs)
      console.error("Error updating parameter ranges:", error);
    }
  }
}

/**
 * Reads the value in B7 (N) and generates/updates the parameter rows (A, B, C) starting at A9.
 * This function handles value generation (parameterX, -10, 10), non-overwrite, and color management 
 * using batch operations for efficiency.
 * * @param {GoogleAppsScript.Spreadsheet.Sheet} sheet The sheet object.
 */
function generateParameterRanges(sheet) {
  const START_ROW = 9; 
  const START_COL_INDEX = 1; // A is the 1st column (1-indexed)
  const COL_COUNT = 3; // Columns A, B, C
  const MAX_ROWS_TO_MANAGE = 500; // Safety limit

  // 1. Get N (the desired number of parameter rows) from B7
  const nRange = sheet.getRange("B7"); 
  let N = parseInt(nRange.getValue());

  // Validate N and apply safety limit
  if (isNaN(N) || N < 0) {
    N = 0;
  }
  if (N > MAX_ROWS_TO_MANAGE) {
    N = MAX_ROWS_TO_MANAGE;
  }

  // 2. Get the color to be used for the new parameters from A8
  const sourceColor = sheet.getRange("A8").getBackground();
  const whiteColor = "#ffffff"; 

  // 3. Define the full range we are managing (A9:C[...]) and read current values
  const fullRange = sheet.getRange(START_ROW, START_COL_INDEX, MAX_ROWS_TO_MANAGE, COL_COUNT); 
  const currentValues = fullRange.getValues();
  
  // Arrays to hold the new values and colors to write back
  const newValues = [];
  const newBackgrounds = [];
  
  // 4. Iterate through the max possible rows to prepare updates
  for (let i = 0; i < MAX_ROWS_TO_MANAGE; i++) {
    const row = currentValues[i];
    const newRowValues = [];
    const newRowColors = [];

    if (i < N) {
      // --- Row Generation Logic (Parameter is needed) ---
      
      const paramIndex = i + 1; 
      const expectedAValue = `parameter${paramIndex}`;
      
      // Column A (Parameter Name) - NOW INCLUDES NON-OVERWRITE CHECK
      const currentA = row[0]; // Get current value in Column A
      newRowValues[0] = (currentA === "" || currentA === null) ? expectedAValue : currentA; // Only set default if cell is empty
      
      // Columns B (Min) and C (Max) - Non-overwrite rule
      // Index 1 (B)
      const currentB = row[1];
      newRowValues[1] = (currentB === "" || currentB === null) ? -10 : currentB; 
      
      // Index 2 (C)
      const currentC = row[2];
      newRowValues[2] = (currentC === "" || currentC === null) ? 10 : currentC;
      
      // Set the background color for the parameter row
      newRowColors[0] = sourceColor;
      newRowColors[1] = sourceColor;
      newRowColors[2] = sourceColor;
      
    } else {
      // --- Row Clearing Logic (Parameter is NOT needed) ---
      
      // Clear values
      newRowValues[0] = "";
      newRowValues[1] = "";
      newRowValues[2] = "";
      
      // Clear colors (set to white)
      newRowColors[0] = whiteColor;
      newRowColors[1] = whiteColor;
      newRowColors[2] = whiteColor;
    }
    
    newValues.push(newRowValues);
    newBackgrounds.push(newRowColors);
  }

  // 5. Write all changes back to the sheet in two batch operations (Values and Colors)
  fullRange.setValues(newValues);
  fullRange.setBackgrounds(newBackgrounds);
}

/**
 * Reads optimizer settings from the "Optimizer Settings" sheet.
 * @returns {Object} Settings object with all optimizer configuration
 */
function readOptimizerSettings() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Optimizer Settings");
  
  function parseParens(str) {
    if (!str) return str;
    const match = str.match(/\(([^)]+)\)/);
    return match ? match[1] : str;
  }
  
  const baseEstimator = parseParens(sheet.getRange("B2").getValue());
  const acquisitionFunction = parseParens(sheet.getRange("B3").getValue());
  const numInitPoints = parseInt(sheet.getRange("B4").getValue()) || 10;
  const batchSize = parseInt(sheet.getRange("B5").getValue()) || 5;
  const numParams = parseInt(sheet.getRange("B7").getValue()) || 0;
  
  // Read parameter specifications starting from row 9
  const paramNames = [];
  const paramMins = [];
  const paramMaxes = [];
  
  for (let i = 0; i < numParams; i++) {
    const row = 9 + i;
    paramNames.push(sheet.getRange(`A${row}`).getValue() || `parameter${i+1}`);
    paramMins.push(parseFloat(sheet.getRange(`B${row}`).getValue()) || 0);
    paramMaxes.push(parseFloat(sheet.getRange(`C${row}`).getValue()) || 10);
  }
  
  return {
    base_estimator: baseEstimator,
    acquisition_function: acquisitionFunction,
    num_init_points: numInitPoints,
    batch_size: batchSize,
    num_params: numParams,
    param_names: paramNames,
    param_mins: paramMins,
    param_maxes: paramMaxes
  };
}

/**
 * Helper function to call Cloud Run endpoint with authentication.
 * @param {string} endpoint - The API endpoint to call
 * @param {Object} payload - The request payload
 * @param {string} initialMessage - Message to show while processing
 */
function callCloudRunEndpoint(endpoint, payload, initialMessage) {
  const ui = SpreadsheetApp.getUi();
  
  // Generate an identity token to authenticate with Cloud Run
  let token;
  try {
    token = ScriptApp.getIdentityToken();
  } catch (e) {
    console.error('Failed to get identity token:', e);
    // Continue without token - let the server decide if it's required
    token = '';
  }

  const options = {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
    headers: token ? {
      'Authorization': 'Bearer ' + token
    } : {}
  };

  // Log request details for debugging
  console.log('Calling endpoint: ' + CLOUD_RUN_URL + endpoint);
  console.log('Payload keys: ' + Object.keys(payload).join(', '));
  console.log('Has token:', token ? 'yes' : 'no');

  ui.alert('In Progress', initialMessage, ui.ButtonSet.OK);

  try {
    const response = UrlFetchApp.fetch(`${CLOUD_RUN_URL}${endpoint}`, options);
    const responseCode = response.getResponseCode();
    const responseBody = response.getContentText();

    console.log('Response code: ' + responseCode);

    if (responseCode === 200) {
      const jsonResponse = JSON.parse(responseBody);
      ui.alert('Success', jsonResponse.message, ui.ButtonSet.OK);
      return jsonResponse;
    } else if (responseCode === 401 || responseCode === 403) {
      const errorTitle = `Authentication Error (${responseCode})`;
      const errorMessage = 
        'The Cloud Run service rejected the request.\n\n' +
        'This usually means:\n' +
        '1. Your Google account is not a Gmail account\n' +
        '2. The identity token could not be validated\n\n' +
        'Full error logged to console.';
      
      console.error(errorTitle);
      console.error('Response body: ' + responseBody);
      
      ui.alert(errorTitle, errorMessage, ui.ButtonSet.OK);
      return null;
    } else {
      const errorTitle = `Error: Service responded with code ${responseCode}`;
      const errorMessage = `The server returned an unexpected response.\n\nCheck the Apps Script logs (View → Logs) for details.`;
      
      console.error(errorTitle);
      console.error('Response body: ' + responseBody);
      
      ui.alert(errorTitle, errorMessage, ui.ButtonSet.OK);
      return null;
    }
  } catch (e) {
    const fatalErrorTitle = 'Fatal Error';
    const fatalErrorMessage = 
      'Could not reach the optimizer service.\n\n' +
      'Error: ' + e.toString() + '\n\n' +
      'Check:\n' +
      '1. Cloud Run URL is correct: ' + CLOUD_RUN_URL + '\n' +
      '2. Service is deployed and running\n' +
      '3. Apps Script logs (View → Logs) for details';
    
    console.error(fatalErrorTitle, fatalErrorMessage);
    console.error('Full error:', e);
    
    ui.alert(fatalErrorTitle, fatalErrorMessage, ui.ButtonSet.OK);
    return null;
  }
}

/**
 * Initialize optimization - generates initial points to evaluate.
 */
function initOptimization() {
  const settings = readOptimizerSettings();
  const payload = { settings: settings };
  callCloudRunEndpoint('/init-optimization', payload, 'Initializing optimization...');
}

/**
 * Continue optimization - generates next batch of points based on results.
 */
function continueOptimization() {
  const settings = readOptimizerSettings();
  // TODO: Read existing data from results sheet
  const existingData = [];
  const payload = { settings: settings, existing_data: existingData };
  callCloudRunEndpoint('/continue-optimization', payload, 'Generating next batch...');
}

/**
 * Test connection to Cloud Run service.
 */
function testCloudRunConnection() {
  callCloudRunEndpoint('/test-connection', {}, 'Testing connection...');
}
