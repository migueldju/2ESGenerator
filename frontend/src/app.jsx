import { Routes, Route } from 'react-router-dom';
import ChatView from './components/ChatView';
import EditorView from './components/EditorView';
import './styles/App.css';

function App() {
  return (
    <Routes>
      <Route path="/" element={<ChatView />} />
      <Route path="/editor" element={<EditorView />} />
    </Routes>
  );
}

export default App;