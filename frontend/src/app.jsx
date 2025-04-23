// Updated App.jsx with proper imports and error handling
import React, { Suspense, lazy } from 'react';
import { Routes, Route } from 'react-router-dom';
import ChatView from './components/chatView';
import EditorView from './components/editorView';
// Import directly instead of using lazy loading for now
import LoginPage from './components/LoginPage';
import RegisterPage from './components/RegisterPage';
import './styles/app.css';

// Fallback component for loading state
const LoadingFallback = () => (
  <div style={{ 
    display: 'flex', 
    justifyContent: 'center', 
    alignItems: 'center', 
    height: '100vh', 
    fontSize: '20px',
    fontWeight: 'bold' 
  }}>
    Loading...
  </div>
);

function App() {
  return (
    <Suspense fallback={<LoadingFallback />}>
      <Routes>
        <Route path="/" element={<ChatView />} />
        <Route path="/editor" element={<EditorView />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Routes>
    </Suspense>
  );
}

export default App;