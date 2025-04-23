import { useState } from 'react';
import { Link } from 'react-router-dom';
import Header from './Header';
import '../styles/AuthPages.css';

const ForgotPasswordPage = () => {
  const [email, setEmail] = useState('');
  const [errors, setErrors] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [requestError, setRequestError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const handleChange = (e) => {
    setEmail(e.target.value);
    
    // Clear error when typing
    if (errors.email) {
      setErrors({});
    }
  };

  const validateForm = () => {
    const newErrors = {};
    
    if (!email) {
      newErrors.email = 'Email is required';
    } else if (!/\S+@\S+\.\S+/.test(email)) {
      newErrors.email = 'Email is invalid';
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setRequestError('');
    setSuccessMessage('');
    
    if (!validateForm()) {
      return;
    }
    
    setIsLoading(true);
    
    try {
      const response = await fetch('/api/forgot-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email }),
        credentials: 'include'
      });
      
      const data = await response.json();
      
      // Even if the email doesn't exist, the API should return a success message 
      // for security reasons (to not reveal which emails are registered)
      setSuccessMessage(data.message || 'If your email is registered, you will receive a password reset link shortly.');
    } catch (error) {
      console.error("Forgot password error:", error);
      setRequestError('An error occurred. Please try again later.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app-container">
      <Header />
      <div className="auth-container">
        <div className="auth-card">
          <h2>Forgot Password</h2>
          <p className="auth-subtitle">Enter your email and we'll send you a link to reset your password</p>
          
          {successMessage && (
            <div className="auth-success-message">
              {successMessage}
            </div>
          )}
          
          {requestError && (
            <div className="auth-error-message">
              {requestError}
            </div>
          )}
          
          <form onSubmit={handleSubmit} className="auth-form">
            <div className="form-group">
              <label htmlFor="email">Email</label>
              <input
                type="email"
                id="email"
                name="email"
                value={email}
                onChange={handleChange}
                placeholder="Enter your email"
                className={errors.email ? 'error' : ''}
              />
              {errors.email && <span className="error-text">{errors.email}</span>}
            </div>
            
            <button 
              type="submit" 
              className="auth-button"
              disabled={isLoading}
            >
              {isLoading ? 'Sending...' : 'Send Reset Link'}
            </button>
          </form>
          
          <div className="auth-footer">
            Remember your password? <Link to="/login">Login here</Link>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ForgotPasswordPage;