import { Link } from '@tanstack/react-router'

export default function Header() {
  const scannerChatUrl = import.meta.env.VITE_CHAT_UI_URL || 'http://localhost:7932'

  return (
    <header className="p-2 d-flex bg-white text-dark justify-content-between">
      <nav className="d-flex">
        <div className="px-2 fw-bold">
          <Link to="/">Home</Link>
        </div>

        <div className="px-2 fw-bold">
          <Link to="/live">Live Firehose</Link>
        </div>

        <div className="px-2 fw-bold">
          <a href={scannerChatUrl} target="_blank" rel="noreferrer">
            Scanner Chat
          </a>
        </div>
      </nav>
    </header>
  )
}
