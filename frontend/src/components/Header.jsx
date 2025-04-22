import { Link } from 'react-router-dom';
import AuthButtons from './AuthButtons';
import '../styles/Header.css';

const Header = () => {
  return (
    <header className="app-header">
      <div className="header-container">
        <div className="logo">
          <Link to="/">
            <h1>ESGenerator</h1>
          </Link>
        </div>
        <div className="header-right">
          <AuthButtons />
        </div>
      </div>
    </header>
  );
};

export default Header;