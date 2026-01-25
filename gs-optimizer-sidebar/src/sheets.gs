/**
 * Extracts content within parentheses, e.g., "Gaussian Process (GP)" -> "GP".
 */
function parseParens(str) {
  if (!str || typeof str !== 'string') return str;
  const match = str.match(/\(([^)]+)\)/);
  return match ? match[1] : str;
}

/**
 * Creates the custom menu when the spreadsheet is opened.
 * This function is automatically triggered by Google Sheets.
 */
function onOpen() {
  try {
    const ui = SpreadsheetApp.getUi();
    ui.createMenu('GSOpt')
        .addItem('Open Sidebar', 'openSidebar')
        .addToUi();
  } catch (e) {
    // Log any errors - check View > Logs in Apps Script editor
    Logger.log('Error creating menu: ' + e.toString());
  }
}

/**
 * Manual function to create the menu - use this for testing.
 * Run this from the Apps Script editor if the menu doesn't appear.
 */
function createMenuManually() {
  onOpen();
  SpreadsheetApp.getUi().alert('Menu created! Check the menu bar for "GSOpt"');
}

/**
 * UI wrapper for connection test
 */
function testConnectionUI() {
  const result = testCloudRunConnection();
  SpreadsheetApp.getUi().alert(result.status + ': ' + result.message);
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
      .setTitle('GSOpt')
      .setWidth(300);
  SpreadsheetApp.getUi().showSidebar(html);
}

/**
 * Opens the parallel coordinates visualization in a larger modeless dialog.
 */
function openParallelCoordinates() {
  const html = HtmlService.createHtmlOutputFromFile('pcp')
      .setWidth(1000)
      .setHeight(700);
  SpreadsheetApp.getUi().showModelessDialog(html, 'Parallel Coordinates Analysis');
}

/**
 * Opens a dialog that loads the plot asynchronously.
 */
function showSkoptPlotDialog(plotType, title) {
  const htmlContent = `
    <!DOCTYPE html>
    <html>
      <head>
        <base target="_top">
        <style>
          body { margin:0; display:flex; flex-direction:column; justify-content:center; align-items:center; height:100vh; background:#ffffff; font-family: sans-serif; }
          .loader { border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin-bottom: 15px; }
          @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
          #status { color: #555; font-size: 16px; margin-bottom: 10px; }
          img { max-width: 98%; max-height: 98%; box-shadow: 0 4px 12px rgba(0,0,0,0.15); display: none; border: 1px solid #ddd; }
          .error { color: #d32f2f; padding: 20px; text-align: center; }
        </style>
      </head>
      <body>
        <div id="loader" class="loader"></div>
        <div id="status">Generating ${title}...<br><span style="font-size:0.8em; color:#888;">This may take a moment</span></div>
        <img id="plotImage" />
        <script>
          window.onload = function() {
            google.script.run
              .withSuccessHandler(function(base64) {
                document.getElementById('loader').style.display = 'none';
                document.getElementById('status').style.display = 'none';
                var img = document.getElementById('plotImage');
                img.src = "data:image/png;base64," + base64;
                img.style.display = 'block';
              })
              .withFailureHandler(function(err) {
                document.getElementById('loader').style.display = 'none';
                document.getElementById('status').innerHTML = '<div class="error">Error generating plot:<br>' + err + '</div>';
              })
              .getPlotData('${plotType}');
          };
        </script>
      </body>
    </html>
  `;
  
  const htmlOutput = HtmlService.createHtmlOutput(htmlContent).setWidth(900).setHeight(700);
  SpreadsheetApp.getUi().showModelessDialog(htmlOutput, title);
}

/**
 * Server-side handler to fetch plot data. Called by the client-side JS in the dialog.
 */
function getPlotData(plotType) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheetInfo = readOptimizerSettings();
  const userEmail = Session.getActiveUser().getEmail();
  const dataSheet = ss.getSheetByName(DATA_SHEET_NAME);
  
  if (!dataSheet) throw new Error("Data sheet not found");

  const lastRow = dataSheet.getLastRow();
  // Ensure we use SKOPT-GP for plotting as it provides the best visual models
  const settings = {
    ...sheetInfo,
    base_estimator: 'SKOPT-GP',
    acquisition_function: 'EI'
  };

  let existingData = [];
  if (lastRow >= DATA_START_ROW) {
    existingData = readDataFromSheet(dataSheet, settings, DATA_START_ROW, lastRow)
      .filter(d => d.objective !== '' && d.objective !== null);
  }

  // Handle Maximization: Negate objective if needed
  const settingsSheet = ss.getSheetByName(SETTINGS_SHEET_NAME);
  const optimizationMode = settingsSheet.getRange(OPTIMIZATION_MODE_CELL).getValue();
  if (optimizationMode === 'Maximize') {
    existingData.forEach(point => {
      // Create copy to be safe, though not strictly necessary here
      point.objective = -1 * parseFloat(point.objective); 
    });
    // Pass mode to backend for better labeling
    settings.optimization_mode = 'Maximize';
  }

  if (existingData.length === 0) {
    throw new Error("No evaluated data available to plot. Please run optimization first.");
  }

  const payload = {
    plot_type: plotType,
    settings: settings,
    existing_data: existingData
  };

  const options = {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    headers: {
      'X-User-Email': userEmail,
      'Authorization': 'Bearer ' + ScriptApp.getIdentityToken()
    },
    muteHttpExceptions: true
  };

  const response = UrlFetchApp.fetch(`${CLOUD_RUN_URL}/plot`, options);
  const responseCode = response.getResponseCode();
  const responseText = response.getContentText();

  if (responseCode !== 200) {
    let errMsg = responseText;
    try {
        const jsonErr = JSON.parse(responseText);
        errMsg = jsonErr.message || responseText;
    } catch(e) {}
    throw new Error(`Server Error (${responseCode}): ${errMsg}`);
  }

  const result = JSON.parse(responseText);
  if (result.status === 'success') {
    return result.plot_data;
  } else {
    throw new Error(result.message);
  }
}

function openConvergencePlot() { showSkoptPlotDialog('convergence', 'Convergence Plot'); }
function openEvaluationsPlot() { showSkoptPlotDialog('evaluations', 'Evaluations Plot'); }
function openObjectivePlot() { showSkoptPlotDialog('objective', 'Objective Plot'); }

/**
 * Fetches data for the PCP visualization.
 */
function getPcpData() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const dataSheet = ss.getSheetByName(DATA_SHEET_NAME);
  if (!dataSheet) return null;
  
  const lastRow = dataSheet.getLastRow();
  if (lastRow < 1) return null;
  
  const values = dataSheet.getDataRange().getValues();
  // Remove the 'Iteration' column (index 0) from headers and rows
  const headers = values[0].slice(1);
  const rows = values.slice(1)
    .filter(row => row[row.length - 1] !== '')
    .map(row => row.slice(1));
  
  return {
    headers: headers,
    rows: rows
  };
}

/**
 * Interface between the sidebar UI and the Sheet/API logic.
 */

function getInitialSettings() {
  return {
    base_estimator: 'GP',
    acquisition_function: 'EI',
    num_params: 2,
    optimization_mode: 'Minimize'
  };
}

function testCloudRunConnection() {
  try {
    const userEmail = Session.getActiveUser().getEmail();
    const options = {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify({}),
      headers: {
        'X-User-Email': userEmail,
        'Authorization': 'Bearer ' + ScriptApp.getIdentityToken()
      },
      muteHttpExceptions: true
    };

    const response = UrlFetchApp.fetch(CLOUD_RUN_URL + '/test-connection', options);
    const code = response.getResponseCode();
    const text = response.getContentText();
    
    if (code === 200) {
      let msg = text;
      try { msg = JSON.parse(text).message; } catch(e) {}
      return { status: 'success', message: msg };
    } else {
      return { status: 'error', message: 'Error (' + code + '): ' + text };
    }
  } catch (e) {
    return { status: 'error', message: e.toString() };
  }
}

/**
 * Logic to communicate with the Cloud Run optimizer backend.
 */
function suggestNextPoints(sidebarSettings, isInit) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheetInfo = readOptimizerSettings();
  const userEmail = Session.getActiveUser().getEmail();
  
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

  // Only read existing evaluation data if we are NOT initializing
  if (!isInit && lastRow >= DATA_START_ROW) {
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

  const endpoint = isInit ? '/init-optimization' : '/continue-optimization';
  const response = UrlFetchApp.fetch(`${CLOUD_RUN_URL}${endpoint}`, options);
  
  if (response.getResponseCode() !== 200) {
    throw new Error(`Cloud Run Error: ${response.getContentText()}`);
  }

  const result = JSON.parse(response.getContentText());
  if (result.data && result.data.length > 0) {
    // If initializing, clear the data sheet first
    if (isInit && lastRow >= DATA_START_ROW) {
      dataSheet.getRange(DATA_START_ROW, 1, lastRow - DATA_START_ROW + 1, dataSheet.getMaxColumns()).clearContent();
      updateDataSheetHeaders(); // Reset formatting/headers
    }
    
    const writeRow = isInit ? DATA_START_ROW : Math.max(DATA_START_ROW, lastRow + 1);
    writePointsToSheet(dataSheet, result.data, settings, writeRow, nextIteration);
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
  
  // Apply data formatting to new rows
  sheet.getRange(startRow, 1, rows.length, 1).setBackground(COLORS.ITER_DATA);
  sheet.getRange(startRow, 2, rows.length, settings.num_params).setBackground(COLORS.PARAM_DATA);
  sheet.getRange(startRow, numCols, rows.length, 1).setBackground(COLORS.OBJ_DATA);
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

  const maxCols = dataSheet.getMaxColumns();
  const maxRows = dataSheet.getMaxRows();

  // Clear ALL headers first
  dataSheet.getRange(1, 1, 1, maxCols).clearContent().setBackground(null);
  
  // Write and style NEW headers
  dataSheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  dataSheet.getRange(1, 1).setBackground(COLORS.ITER_HEADER);
  if (numParams > 0) dataSheet.getRange(1, 2, 1, numParams).setBackground(COLORS.PARAM_HEADER);
  dataSheet.getRange(1, headers.length).setBackground(COLORS.OBJ_HEADER);

  // Style columns for existing data (Row 2 to Max) based on active headers
  if (maxRows > 1) {
    dataSheet.getRange(2, 1, maxRows - 1, 1).setBackground(COLORS.ITER_DATA);
    if (numParams > 0) dataSheet.getRange(2, 2, maxRows - 1, numParams).setBackground(COLORS.PARAM_DATA);
    dataSheet.getRange(2, headers.length, maxRows - 1, 1).setBackground(COLORS.OBJ_DATA);
  }

  // CLEANUP: Effectively delete content and formatting for stale columns
  if (headers.length < maxCols) {
    const startClearCol = headers.length + 1;
    const numClearCols = maxCols - headers.length;
    // Clear the entire column block from Row 1 down to Max Row
    dataSheet.getRange(1, startClearCol, maxRows, numClearCols).clearContent().setBackground(null);
  }
}

function generateParameterRanges(sheet) {
  const numParams = Math.max(0, Math.min(parseInt(sheet.getRange(NUM_PARAMS_CELL).getValue()) || 0, MAX_PARAM_ROWS));
  
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
      newBackgrounds.push([COLORS.PARAM_DATA, COLORS.PARAM_DATA, COLORS.PARAM_DATA]);
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
    .setOption('vAxis', { title: settings.objective_name, viewWindowMode: 'pretty' })
    .setOption('pointSize', 5)
    .setOption('lineWidth', 2)
    .setPosition(rowPos, colPos, 0, 0)
    .build();
  analysisSheet.insertChart(progressChart);
  rowPos += 21;

  // Parameter charts - iterating over all parameters defined in settings
  settings.param_names.forEach((paramName, i) => {
    const paramRange = dataSheet.getRange(DATA_START_ROW, i + 2, numRows, 1);
    const chart = analysisSheet.newChart()
      .asScatterChart()
      .addRange(paramRange)
      .addRange(objectiveRange)
      .setOption('title', `${paramName} vs. Objective`)
      .setOption('hAxis', { title: paramName })
      .setOption('vAxis', { title: settings.objective_name, viewWindowMode: 'pretty' })
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