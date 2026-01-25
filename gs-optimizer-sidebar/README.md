# Google Sheets Bayesian Optimization Sidebar

This project provides a sidebar interface for a Google Sheets integration with a Cloud Run Bayesian optimization service. The sidebar allows users to manage optimization tasks directly from the Google Sheets interface, enhancing usability and accessibility.

## Project Structure

```
gs-optimizer-sidebar
├── src
│   ├── main.gs          # Entry point for the Google Apps Script project
│   ├── api.gs           # Functions for communication with the Cloud Run service
│   ├── sheets.gs        # Functions for interacting with Google Sheets API
│   └── sidebar.html      # HTML structure and layout of the sidebar
├── appsscript.json      # Configuration file for the Google Apps Script project
└── README.md            # Documentation for the project
```

## Features

- Sidebar Interface with controls aligned to the codebase:
  - Initialize and Ask actions
  - Test Connection to Cloud Run
  - Data Plots: Convergence, Evaluations, Objective Partial Dependence (opens modeless dialogs)
  - Parallel Coordinates visualization
- Initialization of Optimization via Cloud Run backend
- Continue Optimization with appended suggestions
- Data Management: read/write points, auto-update headers, and in-sheet charts on the Analysis tab that refresh when objectives change

## Setup Instructions

1. Open Google Sheets: Create or open an existing Google Sheet.
2. Access Script Editor: Click on Extensions → Apps Script to open the editor.
3. Copy Project Files: Create the necessary files as per the project structure outlined above.
4. Deploy the Script: Save and deploy the script as needed.
5. Open the Sidebar: Use Extensions → GSOpt → Open Sidebar.

## Usage

- Initialize to generate initial points; enter objective values in the Data sheet.
- Ask to request new points; enter new objective values.
- Test Connection to verify Cloud Run reachability and permissions.
- Use Data Plots (Convergence, Evaluations, Objective Partial Dependence) and Parallel Coordinates for visualization. Advanced plots open in dialogs; in-sheet charts on the Analysis tab update automatically when editing objective values.

## Notes

- Authentication: The backend expects a Gmail account and Cloud Run invoker permission; identity tokens and the X-User-Email header are sent automatically from Apps Script.


