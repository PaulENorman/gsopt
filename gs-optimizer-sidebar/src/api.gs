/**
 * Logic for calling the optimizer API.
 */
function callOptimizerApi(endpoint, payload) {
  const options = {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };
  
  const response = UrlFetchApp.fetch(CLOUD_RUN_URL + endpoint, options);
  if (response.getResponseCode() !== 200) {
    throw new Error(response.getContentText());
  }
  return JSON.parse(response.getContentText());
}

function initOptimization() {
  const settings = readOptimizerSettings();
  return callOptimizerApi('/init-optimization', { settings: settings });
}

function continueOptimization(existingData) {
  const settings = readOptimizerSettings();
  return callOptimizerApi('/continue-optimization', { settings: settings, existing_data: existingData });
}

function callCloudRunEndpoint(endpoint, payload, progressMessage) {
  /**
   * Makes authenticated API call to Cloud Run service.
   * returns {Object|null} Parsed JSON response or null on error
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

  try {
    const response = UrlFetchApp.fetch(`${CLOUD_RUN_URL}${endpoint}`, options);
    const responseCode = response.getResponseCode();
    const responseBody = response.getContentText();

    console.log(`Response code: ${responseCode}`);

    if (responseCode === 200) {
      const jsonResponse = JSON.parse(responseBody);
      return jsonResponse;
    }
    
    const errorMessage = _buildErrorMessage(responseCode, responseBody, userEmail);
    console.error(`Error ${responseCode}: ${responseBody}`);
    return { status: 'error', message: errorMessage };
    
  } catch (e) {
    const errorMsg = `Could not reach optimizer service.\n\n${e.toString()}\n\nCheck Cloud Run URL: ${CLOUD_RUN_URL}`;
    console.error('Fatal error:', e);
    return { status: 'error', message: errorMsg };
  }
}

function _buildErrorMessage(code, body, email) {
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
  
  return `The server returned an unexpected response: ${parsedError.message || 'Unknown error'}`;
}

function testCloudRunConnection() {
  const result = callCloudRunEndpoint('/test-connection', {});
  return result || { status: 'error', message: 'Failed to connect to Cloud Run' };
}

function ask_for_init_points(sidebarSettings) {
  if (sidebarSettings) {
    saveOptimizerSettings(sidebarSettings);
  }
  
  const dataSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(DATA_SHEET_NAME);
  const sheetInfo = readOptimizerSettings();
  
  // Merge sheet config (params) with sidebar config (algorithm settings)
  const settings = { ...sheetInfo };
  
  if (sidebarSettings) {
    Object.assign(settings, sidebarSettings);
    // Format estimator name for Python backend (e.g., "Gaussian Process (GP)" -> "SKOPT-GP")
    if (sidebarSettings.base_estimator) {
      settings.base_estimator = 'SKOPT-' + parseParens(sidebarSettings.base_estimator);
    }
    if (sidebarSettings.acquisition_function) {
      settings.acquisition_function = parseParens(sidebarSettings.acquisition_function);
    }
  } else {
    // Fallback defaults
    settings.base_estimator = 'SKOPT-GP';
    settings.acquisition_function = 'EI';
    settings.num_init_points = 10;
  }
  
  if (settings.num_params === 0) {
    return { status: 'error', message: 'Please configure parameters first' };
  }
  
  const response = callCloudRunEndpoint('/init-optimization', { settings: settings });
  
  if (response && response.status === 'success' && response.data) {
    const lastRow = dataSheet.getLastRow();
    if (lastRow >= DATA_START_ROW) {
      dataSheet.getRange(DATA_START_ROW, 1, lastRow - DATA_START_ROW + 1, dataSheet.getMaxColumns()).clearContent();
    }
    writePointsToSheet(dataSheet, response.data, settings, DATA_START_ROW, 1);
    return { status: 'success', message: `Initialized with ${response.data.length} points` };
  }
  
  return response || { status: 'error', message: 'Initialization failed' };
}

function tell_ask(sidebarSettings) {
  if (sidebarSettings) {
    saveOptimizerSettings(sidebarSettings);
  }

  const dataSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(DATA_SHEET_NAME);
  const sheetInfo = readOptimizerSettings();
  
  const settings = { ...sheetInfo };
  if (sidebarSettings) {
    Object.assign(settings, sidebarSettings);
    if (sidebarSettings.base_estimator) {
      settings.base_estimator = 'SKOPT-' + parseParens(sidebarSettings.base_estimator);
    }
    if (sidebarSettings.acquisition_function) {
      settings.acquisition_function = parseParens(sidebarSettings.acquisition_function);
    }
  } else {
    settings.base_estimator = 'SKOPT-GP';
    settings.acquisition_function = 'EI';
    settings.batch_size = 5;
  }
  
  const lastRow = dataSheet.getLastRow();
  if (lastRow < DATA_START_ROW) {
    return { status: 'error', message: 'No data found. Initialize first.' };
  }
  
  const existingData = readDataFromSheet(dataSheet, settings, DATA_START_ROW, lastRow);
  const validPointsCount = existingData.filter(point => point.objective !== '' && point.objective !== null).length;
  
  if (validPointsCount === 0) {
    return { status: 'error', message: 'No objective values found in the Data sheet.' };
  }
  
  // Handing maximization. Prioritize sidebar setting if available, else check sheet.
  let isMaximization = false;
  if (sidebarSettings && sidebarSettings.optimization_mode) {
    isMaximization = (sidebarSettings.optimization_mode === 'Maximize');
  } else {
    const settingsSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SETTINGS_SHEET_NAME);
    const mode = settingsSheet.getRange(OPTIMIZATION_MODE_CELL).getValue();
    isMaximization = (mode === 'Maximize');
  }

  if (isMaximization) {
    existingData.forEach(point => {
      if (point.objective !== '' && point.objective !== null) {
        point.objective = -1 * parseFloat(point.objective);
      }
    });
  }

  const response = callCloudRunEndpoint('/continue-optimization', { settings: settings, existing_data: existingData });
  
  if (response && response.status === 'success' && response.data) {
    const nextIteration = (lastRow - DATA_START_ROW + 1) + 1;
    writePointsToSheet(dataSheet, response.data, settings, lastRow + 1, nextIteration);
    return { status: 'success', message: `Added ${response.data.length} new points` };
  }
  
  return response || { status: 'error', message: 'Optimization step failed' };
}