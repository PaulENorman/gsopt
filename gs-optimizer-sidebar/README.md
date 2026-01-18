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

- **Sidebar Interface**: A user-friendly sidebar that provides buttons and input fields for all functionalities related to Bayesian optimization.
- **Initialization of Optimization**: Users can initialize optimization tasks directly from the sidebar.
- **Continue Optimization**: Users can continue optimization processes and append new points to the data.
- **Test Connection**: A feature to test the connection to the Cloud Run service.
- **Data Management**: Functions to read and write data to the Google Sheets, update headers, and manage charts.

## Setup Instructions

1. **Open Google Sheets**: Create or open an existing Google Sheets document.
2. **Access Script Editor**: Click on `Extensions` > `Apps Script` to open the Google Apps Script editor.
3. **Copy Project Files**: Create the necessary files as per the project structure outlined above.
4. **Deploy the Script**: Save and deploy the script as a web app or bound script as needed.
5. **Open the Sidebar**: Use the custom menu created in the Google Sheets interface to open the sidebar and start using the optimization features.

## Usage

- Use the sidebar to initialize optimization, continue optimization, and manage data.
- The sidebar will provide feedback on actions taken and display any relevant messages or errors.

## Contributing

Feel free to contribute to this project by submitting issues or pull requests. Your feedback and contributions are welcome!


