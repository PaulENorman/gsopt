const CLOUD_RUN_URL = 'https://gsopt-449559265504.europe-west1.run.app';
const DATA_SHEET_NAME = 'Data';
const SETTINGS_SHEET_NAME = 'Parameter Settings';
const ANALYSIS_SHEET_NAME = 'Analysis';
const DATA_START_ROW = 2; // Writing to headers on Row 1, data starts Row 2
const PARAM_CONFIG_START_ROW = 6; // Parameters start on Row 6
const MAX_PARAM_ROWS = 500;

const OBJECTIVE_NAME_CELL = 'B2';
const NUM_PARAMS_CELL = 'B4';

/**
 * Extracts content within parentheses, e.g., "Gaussian Process (GP)" -> "GP".
 */
function parseParens(str) {
  if (!str || typeof str !== 'string') return str;
  const match = str.match(/\(([^)]+)\)/);
  return match ? match[1] : str;
}

function onOpen() {
  SpreadsheetApp.getUi()
      .createMenu('Optimizer')
      .addItem('Open Sidebar', 'openSidebar')
      .addToUi();
}

/**
 * Automatically updates headers and parameter ranges when settings change in the "Parameter Settings" sheet.
 */
function onEdit(e) {
  if (!e) return;
  const sheet = e.source.getActiveSheet();
  const range = e.range;
  const sheetName = sheet.getName();
  const a1 = range.getA1Notation();
  const col = range.getColumn();
  const row = range.getRow();

  if (sheetName === SETTINGS_SHEET_NAME) {
    if (a1 === NUM_PARAMS_CELL) {
      generateParameterRanges(sheet);
      updateDataSheetHeaders();
    } else if (a1 === OBJECTIVE_NAME_CELL) {
      updateDataSheetHeaders();
    } else if (col === 1 && row >= PARAM_CONFIG_START_ROW) {
      updateDataSheetHeaders();
    }
  } else if (sheetName === DATA_SHEET_NAME && row >= DATA_START_ROW) {
    // Automatically update plots if the objective column is edited
    const settings = readOptimizerSettings();
    const objectiveCol = settings.num_params + 2;
    if (col === objectiveCol) {
      updateAnalysisPlots();
    }
  }
}

function openSidebar() {
  const html = HtmlService.createHtmlOutputFromFile('sidebar')
      .setTitle('Bayesian Optimizer')
      .setWidth(300);
  SpreadsheetApp.getUi().showSidebar(html);
}

/**
 * Provides the sidebar with initial structural settings from the sheet.
 * Optimizer-specific settings (Estimator, etc.) will use sidebar defaults.
 */
function getInitialSettings() {
  const sheetConfig = readOptimizerSettings();
  return {
    objective_name: sheetConfig.objective_name,
    num_params: sheetConfig.num_params
    // Note: sidebar defaults for GP, EI, etc. will take over from here
  };
}

function ask_for_init_points(settings) {
  return { status: 'success', message: suggestNextPoints(settings) };
}

function tell_ask(settings) {
  return { status: 'success', message: suggestNextPoints(settings) };
}

/**
 * Logic to communicate with the Cloud Run optimizer backend.
 */
function suggestNextPoints(sidebarSettings) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheetInfo = readOptimizerSettings();
  const userEmail = Session.getActiveUser().getEmail();
  
  // Merge: Parameter info from Sheet + Control info from Sidebar
  // Prepend 'SKOPT-' to the estimator as expected by the backend build_optimizer logic
  const settings = {
    ...sheetInfo,
    ...sidebarSettings,
    base_estimator: 'SKOPT-' + parseParens(sidebarSettings.base_estimator),
    acquisition_function: parseParens(sidebarSettings.acquisition_function)
  };

  const dataSheet = ss.getSheetByName(DATA_SHEET_NAME);
  const lastRow = dataSheet.getLastRow();
  let existingData = [];
  let nextIteration = 1;

  const isMinimize = settings.optimization_mode === 'Minimize';

  if (lastRow >= DATA_START_ROW) {
    const allData = readDataFromSheet(dataSheet, settings, DATA_START_ROW, lastRow);
    existingData = allData
      .filter(d => d.objective !== '' && d.objective !== null)
      .map(d => ({
        ...d,
        objective: isMinimize ? -parseFloat(d.objective || 0) : parseFloat(d.objective || 0)
      }));
    nextIteration = lastRow - DATA_START_ROW + 2;
  }

  const payload = {
    settings: { ...settings, minimize: isMinimize },
    existing_data: existingData
  };

  const options = {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
    headers: {
      'X-User-Email': userEmail,
      'Authorization': 'Bearer ' + ScriptApp.getIdentityToken()
    }
  };

  // Uses /continue-optimization as it handles both initial and subsequent states
  const response = UrlFetchApp.fetch(`${CLOUD_RUN_URL}/continue-optimization`, options);
  
  if (response.getResponseCode() !== 200) {
    throw new Error(`Cloud Run Error: ${response.getContentText()}`);
  }

  const result = JSON.parse(response.getContentText());
  if (result.data && result.data.length > 0) {
    writePointsToSheet(dataSheet, result.data, settings, Math.max(DATA_START_ROW, lastRow + 1), nextIteration);
    return result.message || `Generated ${result.data.length} suggestions.`;
  }
  return 'No points suggested.';
}

function saveOptimizerSettings(settings) {
  // We no longer save sidebar-specific optimizer settings to the sheet
  // to keep the "Parameter Settings" tab clean. 
  // We only sync the headers in case names changed.
  updateDataSheetHeaders();
}

/**
 * Reads ONLY the parameter configuration and objective info from the sheet.
 */
function readOptimizerSettings() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SETTINGS_SHEET_NAME);
  
  const numParams = parseInt(sheet.getRange(NUM_PARAMS_CELL).getValue()) || 0;
  const objectiveName = sheet.getRange(OBJECTIVE_NAME_CELL).getValue() || 'Objective';
  
  const paramNames = [];
  const paramMins = [];
  const paramMaxes = [];
  
  if (numParams > 0) {
    const paramData = sheet.getRange(PARAM_CONFIG_START_ROW, 1, numParams, 3).getValues();
    for (let i = 0; i < numParams; i++) {
      paramNames.push(paramData[i][0] || `parameter${i+1}`);
      paramMins.push(parseFloat(paramData[i][1]) || -10);
      paramMaxes.push(parseFloat(paramData[i][2]) || 10);
    }
  }
  
  return {
    objective_name: objectiveName,
    num_params: numParams,
    param_names: paramNames,
    param_mins: paramMins,
    param_maxes: paramMaxes
  };
}

function updateDataSheetHeaders() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const settingsSheet = ss.getSheetByName(SETTINGS_SHEET_NAME);
  const dataSheet = ss.getSheetByName(DATA_SHEET_NAME);

  if (!dataSheet || !settingsSheet) return;

  const numParams = parseInt(settingsSheet.getRange(NUM_PARAMS_CELL).getValue()) || 0;
  const objectiveName = settingsSheet.getRange(OBJECTIVE_NAME_CELL).getValue() || 'Objective';
  const headers = ['Iteration'];

  if (numParams > 0) {
    const paramNames = settingsSheet.getRange(PARAM_CONFIG_START_ROW, 1, numParams).getValues();
    paramNames.forEach(row => headers.push(row[0] || `p${headers.length}`));
  }
  headers.push(objectiveName);

  dataSheet.getRange(1, 1, 1, dataSheet.getMaxColumns()).clearContent();
  dataSheet.getRange(1, 1, 1, headers.length).setValues([headers]);
}

function generateParameterRanges(sheet) {
  const numParams = Math.max(0, Math.min(parseInt(sheet.getRange(NUM_PARAMS_CELL).getValue()) || 0, MAX_PARAM_ROWS));
  const sourceColor = sheet.getRange('A5').getBackground(); // Style reference
  
  const fullRange = sheet.getRange(PARAM_CONFIG_START_ROW, 1, MAX_PARAM_ROWS, 3);
  const currentValues = fullRange.getValues();
  const newValues = [];
  const newBackgrounds = [];
  
  for (let i = 0; i < MAX_PARAM_ROWS; i++) {
    if (i < numParams) {
      newValues.push([
        currentValues[i][0] || `parameter${i + 1}`,
        (currentValues[i][1] === '' || currentValues[i][1] === null) ? -10 : currentValues[i][1],
        (currentValues[i][2] === '' || currentValues[i][2] === null) ? 10 : currentValues[i][2]
      ]);
      newBackgrounds.push([sourceColor, sourceColor, sourceColor]);
    } else {
      newValues.push(['', '', '']);
      newBackgrounds.push(['#ffffff', '#ffffff', '#ffffff']);
    }
  }
  fullRange.setValues(newValues).setBackgrounds(newBackgrounds);
}

function readDataFromSheet(sheet, settings, startRow, endRow) {
  const numCols = settings.num_params + 1; // Params + Objective
  const range = sheet.getRange(startRow, 2, endRow - startRow + 1, numCols);
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

function writePointsToSheet(sheet, points, settings, startRow, startIteration) {
  const rows = points.map((point, index) => {
    const row = [startIteration + index]; // Iteration
    settings.param_names.forEach(name => row.push(point[name] || 0)); // Params
    row.push(''); // Objective
    return row;
  });
  
  const numCols = settings.num_params + 2; // Iteration + Params + Objective
  const range = sheet.getRange(startRow, 1, rows.length, numCols);
  range.setValues(rows);
}

function updateAnalysisPlots() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const analysisSheet = ss.getSheetByName(ANALYSIS_SHEET_NAME);
  const dataSheet = ss.getSheetByName(DATA_SHEET_NAME);

  if (!analysisSheet || !dataSheet) return;

  deleteAnalysisPlots(); // Clear old charts

  const settings = readOptimizerSettings();
  const lastRow = dataSheet.getLastRow();
  if (lastRow < DATA_START_ROW) return;

  const numRows = lastRow - DATA_START_ROW + 1;
  const objectiveCol = settings.num_params + 2;

  const iterationRange = dataSheet.getRange(DATA_START_ROW, 1, numRows, 1);
  const objectiveRange = dataSheet.getRange(DATA_START_ROW, objectiveCol, numRows, 1);

  let rowPos = 2;
  const colPos = 2;

  // Progress Chart: Objective vs. Iteration
  const progressChart = analysisSheet.newChart()
    .asScatterChart()
    .addRange(iterationRange)
    .addRange(objectiveRange)
    .setOption('title', 'Objective vs. Iteration')
    .setOption('hAxis', { title: 'Iteration' })
    .setOption('vAxis', { title: 'Objective', viewWindowMode: 'pretty' }) // Ensure scaling to objective values
    .setOption('pointSize', 5)
    .setOption('lineWidth', 2)
    .setPosition(rowPos, colPos, 0, 0)
    .build();
  analysisSheet.insertChart(progressChart);
  rowPos += 21;

  // Parameter charts (One for each actual parameter name found in settings)
  settings.param_names.forEach((paramName, i) => {
    const paramRange = dataSheet.getRange(DATA_START_ROW, i + 2, numRows, 1);
    const chart = analysisSheet.newChart()
      .asScatterChart()
      .addRange(paramRange)
      .addRange(objectiveRange)
      .setOption('title', `${paramName} vs. Objective`)
      .setOption('hAxis', { title: paramName })
      .setOption('vAxis', { title: 'Objective' })
      .setOption('pointSize', 5)
      .setPosition(rowPos, colPos, 0, 0)
      .build();
    analysisSheet.insertChart(chart);
    rowPos += 21;
  });
}

function deleteAnalysisPlots() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const analysisSheet = ss.getSheetByName(ANALYSIS_SHEET_NAME);
  if (!analysisSheet) return;
  const charts = analysisSheet.getCharts();
  for (let i = 0; i < charts.length; i++) {
    analysisSheet.removeChart(charts[i]);
  }
}

function testCloudRunConnection() {
  const userEmail = Session.getActiveUser().getEmail();
  try {
    const options = {
      method: 'post',
      contentType: 'application/json',
      muteHttpExceptions: true,
      headers: {
        'X-User-Email': userEmail,
        'Authorization': 'Bearer ' + ScriptApp.getIdentityToken()
      },
      payload: JSON.stringify({})
    };
    
    const response = UrlFetchApp.fetch(`${CLOUD_RUN_URL}/test-connection`, options);
    const code = response.getResponseCode();
    const content = response.getContentText();
    
    if (code === 200) {
       return { status: 'success', message: 'Connected: ' + content };
    } else {
       return { status: 'error', message: `Server returned ${code}: ${content}` };
    }
  } catch (e) {
    return { status: 'error', message: 'Connection failed: ' + e.toString() };
  }
}