function onOpen() {
  /**
   * Creates custom menu when spreadsheet opens.
   */
  SpreadsheetApp.getUi()
      .createMenu('Optimizer')
      .addItem('Open Sidebar', 'openSidebar')
      .addToUi();
}

function openSidebar() {
  /**
   * Opens the sidebar in the Google Sheets UI.
   */
  const html = HtmlService.createHtmlOutputFromFile('sidebar')
      .setTitle('Optimizer Control Panel')
      .setSandboxMode(HtmlService.SandboxMode.IFRAME)
      .setWidth(300);
  SpreadsheetApp.getUi().showSidebar(html);
}

function getInitialSettings() {
  return readOptimizerSettings();
}

function onEdit(e) {
  /**
   * Automatically updates parameter ranges when number of parameters changes.
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
      } catch (error) {
        console.error('Error updating analysis plots:', error);
      }
    }
  }
}