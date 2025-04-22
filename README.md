# ESGenerator - ESRS Reporting Tool

Application to help companies to create their ESG report according to the European Sustainability Reporting Standards (ESRS) mandatory for most of companies operating in Europe since the release of the Corporate Sustainability Reporting Directive (CSRD). 

## Project Structure

```
esrs-generator/
├── backend/               # Flask backend
│   ├── app.py             # Main Flask application
│   ├── vectorstores/      # Vector databases for different sectors
│   └── requirements.txt   # Python dependencies
├── frontend/              # React frontend
│   ├── public/            # Static assets
│   ├── src/               # React components and styles
│   ├── index.html         # HTML template
│   ├── package.json       # NPM dependencies
│   └── vite.config.js     # Vite configuration
└── README.md              # Project documentation
```

## Setup Instructions

### Backend Setup

1. Navigate to the backend directory:
   ```
   cd backend
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   ```

3. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - macOS/Linux: `source venv/bin/activate`

4. Install dependencies:
   ```
   pip install -r requirements.txt 

   # Note: this file will be added shortly.
   ```

### Frontend Setup

1. Navigate to the frontend directory:
   ```
   cd frontend
   ```

2. Install NPM dependencies:
   ```
   npm install
   ```

3. Build the frontend (for production):
   ```
   npm run build
   ```

   Or start the development server:
   ```
   npm run dev
   ```

### Running the Application

1. Start the Flask backend (from the backend directory):
   ```
   flask run
   ```

2. For development, run the Vite dev server (from the frontend directory):
   ```
   npm run dev
   ```

3. For production, build the frontend and serve it through Flask:
   ```
   cd frontend
   npm run build
   cd ../backend
   flask run
   ```

4. Open your browser and navigate to:
   - Development: `http://localhost:5173`
   - Production: `http://localhost:5000`
