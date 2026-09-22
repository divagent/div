import brandLogo from '../assets/logo/ChatGPT_Image_May_20__2026__10_03_18_AM-removebg-preview.png'

export function AppHeader() {
  return (
    <header className="top-rail">
      <div className="brand-lockup">
        <img src={brandLogo} alt="Dividend AI" />
        <div>
          <strong>Dividend AI</strong>
          <span>Income calendar intelligence</span>
        </div>
      </div>
      <div className="header-actions">
        <button className="ghost-button" type="button">
          Log in
        </button>
        <button className="primary-button auth-button" type="button">
          Sign up
        </button>
      </div>
    </header>
  )
}
