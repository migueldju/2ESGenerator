import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faPaperPlane, faRedo } from '@fortawesome/free-solid-svg-icons';
import Header from './Header';
import '../styles/chatView.css';

const ChatView = () => {
  const [messages, setMessages] = useState([
    {
      type: 'bot',
      content: `<h2>Welcome to ESGenerator</h2>
                <p>Please provide a detailed description of your company's activities, products, services, and sector to help me determine the applicable ESRS reporting standards.</p>`,
      isWelcome: true
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [companyInfo, setCompanyInfo] = useState({
    initialized: false,
    naceSector: 'Not classified yet',
    esrsSector: 'Not determined yet'
  });

  const chatContainerRef = useRef(null);
  const textareaRef = useRef(null);
  const navigate = useNavigate();

  const [placeholderText, setPlaceholder] = useState("Enter your company description...");
  const [companyDesc, setCompanyDesc] = useState('');
  const [conversationHistory, setConversationHistory] = useState([]);

  // Scroll to bottom when messages change
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [messages]);

  // Adjust textarea height automatically
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
      
      if (textareaRef.current.scrollHeight > 150) {
        textareaRef.current.style.overflowY = 'scroll';
        textareaRef.current.style.height = '150px';
      } else {
        textareaRef.current.style.overflowY = 'hidden';
      }
    }
  }, [inputValue]);

  // Check for existing session on component mount
  useEffect(() => {
    const checkSession = async () => {
      try {
        const response = await fetch('/api/check_session', {
          method: 'GET',
          credentials: 'include'
        });
        
        if (response.ok) {
          const data = await response.json();
          if (data.initialized) {
            setCompanyInfo({
              initialized: true,
              naceSector: data.nace_sector,
              esrsSector: data.esrs_sector
            });
            setPlaceholder("Ask your question here...");
          }
        }
      } catch (error) {
        console.error('Error checking session:', error);
      }
    };
    
    checkSession();
  }, []);

  const handleInputChange = (e) => {
    setInputValue(e.target.value);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };
  
  const handleSendMessage = async () => {
    if (!inputValue.trim()) return;
  
    setMessages(prev => [...prev, { type: 'user', content: inputValue }]);
    
    const currentInput = inputValue;
    setInputValue('');
    
    setIsLoading(true);
  
    try {
      const formData = new FormData();
      formData.append('message', currentInput);
      
      const response = await fetch('/api/chat', {
        method: 'POST',
        body: formData,
        credentials: 'include'
      });
  
      const data = await response.json();
  
      if (data.is_first_message) {
        setCompanyInfo({
          initialized: true,
          naceSector: data.nace_sector,
          esrsSector: data.esrs_sector
        });
        setCompanyDesc(currentInput);
        setPlaceholder("Ask your question here...");
      } 
  
      setMessages(prev => [...prev, { type: 'bot', content: data.answer }]);
    } catch (error) {
      console.error('Error:', error);
      setMessages(prev => [...prev, { 
        type: 'bot', 
        content: "I'm sorry, there was an error processing your request. Please try again." 
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = async () => {
    try {
      const response = await fetch('/api/reset', {
        method: 'POST',
        credentials: 'include'
      });
      
      if (response.ok) {
        setMessages([
          {
            type: 'bot',
            content: `<h2>Welcome to ESGenerator</h2>
                      <p>Please provide a detailed description of your company's activities, products, services, and sector to help me determine the applicable ESRS reporting standards.</p>`,
            isWelcome: true
          }
        ]);
        setInputValue('');
        setCompanyInfo({
          initialized: false,
          naceSector: 'Not classified yet',
          esrsSector: 'Not determined yet'
        });
        setPlaceholder("Enter your company description...");
      }
    } catch (error) {
      console.error('Error resetting chat:', error);
    }
  };

  return (
    <div className="app-container">
      <Header />
      <div className="main-content">
        <div className="container">
          <div className="nav-container">
            <button className="nav-button active">Chat</button>
            <button 
              className="nav-button inactive" 
              onClick={() => navigate('/editor')}
            >
              Editor
            </button>
          </div>
          
          {companyInfo.initialized && (
            <div className="sub-header">
              <div className="sector-info">
                <div className="sector-box">
                  <h3>NACE Sector:</h3>
                  <p>{companyInfo.naceSector}</p>
                </div>
                <div className="sector-box">
                  <h3>Sector-specific Standards:</h3>
                  <p>{companyInfo.esrsSector}</p>
                </div>
                <button 
                  className="reset-button" 
                  title="Start new conversation"
                  onClick={handleReset}
                >
                  <FontAwesomeIcon icon={faRedo} /> New Chat
                </button>
              </div>
            </div>
          )}
          
          <div className="chat-container" ref={chatContainerRef}>
            {messages.map((message, index) => (
              <div 
                key={index} 
                className={`message ${message.type}-message ${message.isWelcome ? 'welcome-message' : ''}`}
                dangerouslySetInnerHTML={{ __html: message.content }}
              />
            ))}
            
            {isLoading && (
              <div className="message bot-message loading">
                <div className="loading-dots">
                  <div className="dot"></div>
                  <div className="dot"></div>
                  <div className="dot"></div>
                </div>
              </div>
            )}
          </div>
          
          <div className="input-container">
            <textarea
              ref={textareaRef}
              id="user-input"
              value={inputValue}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder={placeholderText}
              rows="1"
            />
            <button 
              id="send-button"
              onClick={handleSendMessage}
              disabled={isLoading || !inputValue.trim()}
            >
              <FontAwesomeIcon icon={faPaperPlane} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatView;