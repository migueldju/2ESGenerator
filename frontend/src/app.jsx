import { Routes, Route } from 'react-router-dom';
import ChatView from './components/chatView';
import EditorView from './components/editorView';
import './styles/app.css';

function App() {
  return (
    <Routes>
      <Route path="/" element={<ChatView />} />
      <Route path="/editor" element={<EditorView />} />
    </Routes>
  );
}

export default App;