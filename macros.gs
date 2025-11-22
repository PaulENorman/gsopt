/**
 * Google Sheets Bayesian Optimization Integration
 * 
 * This script provides integration between Google Sheets and a Cloud Run
 * Bayesian optimization service. It handles parameter configuration,
 * data reading/writing, and communication with the optimizer API.
 */

const CLOUD_RUN_URL = 'https://gsopt-449559265504.europe-west1.run.app';
const DATA_SHEET_NAME = 'Data';
const SETTINGS_SHEET_NAME = 'Optimizer Settings';
const DATA_START_ROW = 4;
const PARAM_CONFIG_START_ROW = 9;
const MAX_PARAM_ROWS = 500;


function onOpen() {
  /**
   * Creates custom menu when spreadsheet opens.
   */
  SpreadsheetApp.getUi()
      .createMenu('Optimizer')
      .addItem('1. Initialize Optimization', 'initOptimization')
      .addItem('2. Continue Optimization', 'continueOptimization')
      .addSeparator()
      .addItem('Test Connection', 'testCloudRunConnection')
      .addToUi();
}


function onEdit(e) {
  /**
   * Automatically updates parameter ranges when number of parameters changes.
   * 
   * @param {GoogleAppsScript.Events.SheetsOnEdit} e - The edit event object
   */
  if (!e || !e.range) return;
  
  const sheet = e.range.getSheet();
  const editedCell = e.range.getA1Notation();

  if (sheet.getName() === SETTINGS_SHEET_NAME && editedCell === 'B7') {
    try {
      generateParameterRanges(sheet);
    } catch (error) {
      console.error('Error updating parameter ranges:', error);
    }
  }
}


function generateParameterRanges(sheet) {
  /**
   * Generates or updates parameter configuration rows based on the number specified in B7.
   * Creates default parameter names, mins, and maxes while preserving existing values.
   * 
   * @param {GoogleAppsScript.Spreadsheet.Sheet} sheet - The Optimizer Settings sheet
   */
  const numParams = Math.max(0, Math.min(parseInt(sheet.getRange('B7').getValue()) || 0, MAX_PARAM_ROWS));
  const sourceColor = sheet.getRange('A8').getBackground();
  const whiteColor = '#ffffff';
  
  const fullRange = sheet.getRange(PARAM_CONFIG_START_ROW, 1, MAX_PARAM_ROWS, 3);
  const currentValues = fullRange.getValues();
  
  const newValues = [];
  const newBackgrounds = [];
  
  for (let i = 0; i < MAX_PARAM_ROWS; i++) {
    const row = currentValues[i];
    
    if (i < numParams) {
      newValues.push([
        row[0] || `parameter${i + 1}`,
        row[1] === '' || row[1] === null ? -10 : row[1],
        row[2] === '' || row[2] === null ? 10 : row[2]
      ]);
      newBackgrounds.push([sourceColor, sourceColor, sourceColor]);
    } else {
      newValues.push(['', '', '']);
      newBackgrounds.push([whiteColor, whiteColor, whiteColor]);
    }
  }
  
  fullRange.setValues(newValues);
  fullRange.setBackgrounds(newBackgrounds);
}


function readOptimizerSettings() {
  /**
   * Reads all optimizer configuration from the Settings sheet.
   * 
   * @returns {Object} Settings object with optimizer configuration
   */
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SETTINGS_SHEET_NAME);
  
  const parseParens = str => {
    if (!str) return str;
    const match = str.match(/\(([^)]+)\)/);
    return match ? match[1] : str;
  };
  
  const numParams = parseInt(sheet.getRange('B7').getValue()) || 0;
  const paramNames = [];
  const paramMins = [];
  const paramMaxes = [];
  
  for (let i = 0; i < numParams; i++) {
    const row = PARAM_CONFIG_START_ROW + i;
    paramNames.push(sheet.getRange(`A${row}`).getValue() || `parameter${i+1}`);
    paramMins.push(parseFloat(sheet.getRange(`B${row}`).getValue()) || 0);
    paramMaxes.push(parseFloat(sheet.getRange(`C${row}`).getValue()) || 10);
  }
  
  return {
    base_estimator: parseParens(sheet.getRange('B2').getValue()),
    acquisition_function: parseParens(sheet.getRange('B3').getValue()),
    num_init_points: parseInt(sheet.getRange('B4').getValue()) || 10,
    batch_size: parseInt(sheet.getRange('B5').getValue()) || 5,
    num_params: numParams,
    param_names: paramNames,
    param_mins: paramMins,
    param_maxes: paramMaxes
  };
}


function callCloudRunEndpoint(endpoint, payload, progressMessage) {
  /**
   * Makes authenticated API call to Cloud Run service.
   * 
   * @param {string} endpoint - API endpoint path
   * @param {Object} payload - JSON payload
   * @param {string} progressMessage - Message to display during processing
   * @returns {Object|null} Parsed JSON response or null on error
   */
  const ui = SpreadsheetApp.getUi();
  const userEmail = Session.getActiveUser().getEmail();
  
  if (!userEmail || !userEmail.endsWith('@gmail.com')) {
    ui.alert('Authentication Error',
             `This service requires a Gmail account.\n\nYour account: ${userEmail || 'unknown'}`,
             ui.ButtonSet.OK);
    return null;
  }
  
  let token = '';
  try {
    token = ScriptApp.getIdentityToken();
    console.log('Successfully generated identity token');
  } catch (e) {
    console.error('Failed to get identity token:', e);
  }

  const headers = { 'X-User-Email': userEmail };
  if (token) headers['Authorization'] = 'Bearer ' + token;

  const options = {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
    headers: headers
  };

  console.log(`Calling: ${CLOUD_RUN_URL}${endpoint}`);
  console.log(`User: ${userEmail}`);

  ui.alert('In Progress', progressMessage, ui.ButtonSet.OK);

  try {
    const response = UrlFetchApp.fetch(`${CLOUD_RUN_URL}${endpoint}`, options);
    const responseCode = response.getResponseCode();
    const responseBody = response.getContentText();

    console.log(`Response code: ${responseCode}`);
    console.log(`Response preview: ${responseBody.substring(0, 200)}`);

    if (responseCode === 200) {
      const jsonResponse = JSON.parse(responseBody);
      ui.alert('Success', jsonResponse.message, ui.ButtonSet.OK);
      return jsonResponse;
    }
    
    const errorMessage = _buildErrorMessage(responseCode, responseBody, userEmail);
    console.error(`Error ${responseCode}: ${responseBody}`);
    ui.alert(`Error (${responseCode})`, errorMessage, ui.ButtonSet.OK);
    return null;
    
  } catch (e) {
    const errorMsg = `Could not reach optimizer service.\n\n${e.toString()}\n\nCheck Cloud Run URL: ${CLOUD_RUN_URL}`;
    console.error('Fatal error:', e);
    ui.alert('Fatal Error', errorMsg, ui.ButtonSet.OK);
    return null;
  }
}


function _buildErrorMessage(code, body, email) {
  /**
   * Builds user-friendly error message based on response code.
   * 
   * @param {number} code - HTTP response code
   * @param {string} body - Response body
   * @param {string} email - User email
   * @returns {string} Formatted error message
   */
  let parsedError;
  try {
    parsedError = JSON.parse(body);
  } catch (e) {
    parsedError = { message: body };
  }
  
  if (code === 401 || code === 403) {
    return `The Cloud Run service rejected the request.\n\n` +
           `Server message: ${parsedError.message || 'Unknown error'}\n\n` +
           `Your account: ${email}\n\n` +
           `Required:\n` +
           `1. Must use a Gmail account (@gmail.com)\n` +
           `2. Cloud Run must allow your account as invoker`;
  }
  
  return `The server returned an unexpected response.\n\nCheck Apps Script logs (View → Logs) for details.`;
}


function initOptimization() {
  /**
   * Menu item: Initialize optimization using settings from Settings sheet.
   */
  const settings = readOptimizerSettings();
  callCloudRunEndpoint('/init-optimization', { settings: settings }, 'Initializing optimization...');
}


function continueOptimization() {
  /**
   * Menu item: Continue optimization (placeholder - use ask_for_init_points and tell_ask instead).
   */
  const settings = readOptimizerSettings();
  callCloudRunEndpoint('/continue-optimization', { settings: settings, existing_data: [] }, 'Generating next batch...');
}


function testCloudRunConnection() {
  /**
   * Menu item: Tests connection and authentication to Cloud Run service.
   */
  callCloudRunEndpoint('/test-connection', {}, 'Testing connection...');
}


function ask_for_init_points() {
  /**
   * Button handler: Initializes optimization and writes initial points to Data sheet.
   * Clears existing data and writes new initial points starting at row 4.
   */
  const ui = SpreadsheetApp.getUi();
  const dataSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(DATA_SHEET_NAME);
  
  if (!dataSheet) {
    ui.alert('Error', `Could not find sheet named "${DATA_SHEET_NAME}"`, ui.ButtonSet.OK);
    return;
  }
  
  const settings = readOptimizerSettings();
  
  if (settings.num_params === 0) {
    ui.alert('Error', 'Please configure parameters in the Optimizer Settings sheet first', ui.ButtonSet.OK);
    return;
  }
  
  const response = callCloudRunEndpoint('/init-optimization', { settings: settings }, 'Generating initial points...');
  
  if (!response || response.status !== 'success' || !response.data || response.data.length === 0) {
    return;
  }
  
  _writePointsToSheet(dataSheet, response.data, settings, DATA_START_ROW);
  console.log(`Wrote ${response.data.length} initial points to Data sheet`);
}


function tell_ask() {
  /**
   * Button handler: Reads evaluated data, continues optimization, and appends new points.
   * Validates that at least some objective values have been filled in before continuing.
   */
  const ui = SpreadsheetApp.getUi();
  const dataSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(DATA_SHEET_NAME);
  
  if (!dataSheet) {
    ui.alert('Error', `Could not find sheet named "${DATA_SHEET_NAME}"`, ui.ButtonSet.OK);
    return;
  }
  
  const settings = readOptimizerSettings();
  
  if (settings.num_params === 0) {
    ui.alert('Error', 'Please configure parameters in the Optimizer Settings sheet first', ui.ButtonSet.OK);
    return;
  }
  
  const lastRow = dataSheet.getLastRow();
  
  if (lastRow < DATA_START_ROW) {
    ui.alert('Error', 'No data found. Please run "Initialize" first.', ui.ButtonSet.OK);
    return;
  }
  
  const existingData = _readDataFromSheet(dataSheet, settings, DATA_START_ROW, lastRow);
  
  const validPointsCount = existingData.filter(point => point.objective !== '' && point.objective !== null).length;
  
  console.log(`Read ${existingData.length} total points (${validPointsCount} with objectives)`);
  console.log(`Sample: ${JSON.stringify(existingData[0])}`);
  
  if (validPointsCount === 0) {
    ui.alert('Warning',
             'No evaluated points found (objective column is empty).\n\n' +
             'Please fill in at least some objective values before continuing.',
             ui.ButtonSet.OK);
    return;
  }
  
  const response = callCloudRunEndpoint(
    '/continue-optimization',
    { settings: settings, existing_data: existingData },
    'Generating next batch...'
  );
  
  if (!response || response.status !== 'success' || !response.data || response.data.length === 0) {
    return;
  }
  
  _writePointsToSheet(dataSheet, response.data, settings, lastRow + 1);
  console.log(`Appended ${response.data.length} new points at row ${lastRow + 1}`);
}


function _readDataFromSheet(sheet, settings, startRow, endRow) {
  /**
   * Reads data points from sheet and converts to array of objects.
   * 
   * @param {GoogleAppsScript.Spreadsheet.Sheet} sheet - Data sheet
   * @param {Object} settings - Optimizer settings
   * @param {number} startRow - First row to read
   * @param {number} endRow - Last row to read
   * @returns {Array<Object>} Array of data points with parameter and objective values
   */
  const numCols = settings.num_params + 1;
  const range = sheet.getRange(startRow, 1, endRow - startRow + 1, numCols);
  const values = range.getValues();
  
  return values.map(row => {
    const point = {};
    settings.param_names.forEach((name, i) => {
      point[name] = row[i];
    });
    point.objective = row[settings.num_params];
    return point;
  });
}


function _writePointsToSheet(sheet, points, settings, startRow) {
  /**
   * Writes points to sheet starting at specified row.
   * 
   * @param {GoogleAppsScript.Spreadsheet.Sheet} sheet - Data sheet
   * @param {Array<Object>} points - Points to write
   * @param {Object} settings - Optimizer settings
   * @param {number} startRow - Row to start writing
   */
  const rows = points.map(point => {
    const row = settings.param_names.map(name => point[name] || 0);
    row.push('');
    return row;
  });
  
  const numCols = settings.num_params + 1;
  const range = sheet.getRange(startRow, 1, rows.length, numCols);
  range.setValues(rows);
}
