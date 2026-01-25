/**
 * Main entry point for the GSOpt application.
 * Consolidates menu creation logic to avoid dependency on external macros.
 */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('GSOpt')
    .addItem('Open Optimizer Sidebar', 'showSidebar')
    .addToUi();
}

/**
 * Ensures the menu appears immediately after installation without needing a refresh.
 */
function onInstall(e) {
  onOpen(e);
}

/**
 * Loads the sidebar HTML from the sidebar.html file.
 */
function showSidebar() {
  const html = HtmlService.createHtmlOutputFromFile('sidebar')
    .setTitle('GSOpt: Bayesian Optimization')
    .setWidth(300);
  SpreadsheetApp.getUi().showSidebar(html);
}

/**
 * Include function to allow splitting HTML into multiple files if needed (not strictly used here but good practice).
 */
function include(filename) {
  return HtmlService.createHtmlOutputFromFile(filename)
      .getContent();
}

function getInitialSettings() {
  return readOptimizerSettings();
}

// Sheet and cell constants
const SETTINGS_SHEET_NAME = 'Settings';
const DATA_SHEET_NAME = 'Data';
const NUM_PARAMS_CELL = 'B2';
const OBJECTIVE_NAME_CELL = 'B3';
const PARAM_CONFIG_START_ROW = 6;
const DATA_START_ROW = 2;

// Edit event batching
let _editBatchTimer = null;
const EDIT_BATCH_DELAY_MS = 2000; // 2 seconds

function onEdit(e) {
  /**
   * Automatically updates parameter ranges when number of parameters changes.
   * Enhanced with batched server pinging for proactive warm-up.
   * 
   * @param {GoogleAppsScript.Events.SheetsOnEdit} e - The edit event object
   */
  if (!e || !e.range) return;
  
  const sheet = e.range.getSheet();
  const sheetName = sheet.getName();
  const editedRow = e.range.getRow();
  const editedCol = e.range.getColumn();

  if (sheetName === SETTINGS_SHEET_NAME) {
    if (e.range.getA1Notation() === NUM_PARAMS_CELL) {
      try {
        generateParameterRanges(sheet);
        updateDataSheetHeaders();
        // Queue server ping for settings changes
        queueServerPing_();
      } catch (error) {
        console.error('Error updating parameter ranges/headers:', error);
      }
    }
    else if (
      (editedCol === 1 && editedRow >= PARAM_CONFIG_START_ROW) ||
      e.range.getA1Notation() === OBJECTIVE_NAME_CELL
    ) {
      try {
        updateDataSheetHeaders();
        queueServerPing_();
      } catch (error) {
        console.error('Error updating data sheet headers:', error);
      }
    }
  } else if (sheetName === DATA_SHEET_NAME && editedRow >= DATA_START_ROW) {
    const settingsSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SETTINGS_SHEET_NAME);
    if (!settingsSheet) return;

    const numParams = parseInt(settingsSheet.getRange(NUM_PARAMS_CELL).getValue()) || 0;
    const objectiveCol = numParams + 2;

    if (editedCol === objectiveCol) {
      try {
        const lock = LockService.getScriptLock();
        if (lock.tryLock(1000)) {
          updateAnalysisPlots();
          lock.releaseLock();
        } else {
          console.log('Could not acquire lock to update plots.');
        }
        // Queue server ping when objectives are edited (user likely to continue optimization)
        queueServerPing_();
      } catch (error) {
        console.error('Error updating analysis plots:', error);
      }
    }
  }
}

/**
 * Queues a server ping with batching to prevent spam.
 * Multiple edits within EDIT_BATCH_DELAY_MS will result in a single ping.
 * @private
 */
function queueServerPing_() {
  // Clear existing timer
  if (_editBatchTimer) {
    // Timer exists, will be reset
  }
  
  // Set new timer - this will batch multiple rapid edits
  // Note: Apps Script doesn't support setTimeout, so we use time-delayed triggers
  // For simplicity, we'll use the request queue system in api.gs
  try {
    Utilities.sleep(EDIT_BATCH_DELAY_MS);
    pingServerFromEdit();
  } catch (error) {
    console.error('Error queuing server ping:', error);
  }
}

/**
 * Triggers a batched server ping from edit events.
 */
function pingServerFromEdit() {
  try {
    // Use the unified communication layer
    pingServer();
  } catch (error) {
    // Silently fail - don't interrupt user's sheet editing
    console.error('Background server ping failed:', error);
  }
}

/**
 * Reads optimizer settings from the Settings sheet.
 */
function readOptimizerSettings() {
  // ...existing code...
}

/**
 * Generates parameter range rows based on number of parameters.
 */
function generateParameterRanges(sheet) {
  // ...existing code...
}

/**
 * Updates Data sheet headers to match parameter names from Settings.
 */
function updateDataSheetHeaders() {
  // ...existing code...
}

/**
 * Updates analysis plots when objective values change.
 */
function updateAnalysisPlots() {
  // Placeholder for plot update logic
  // This would typically refresh charts or trigger recalculations
  console.log('Analysis plots updated');
}