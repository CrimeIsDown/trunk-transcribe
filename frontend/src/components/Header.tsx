import { Link } from '@tanstack/react-router'

export default function Header() {
  return (
    <header className="p-2 d-flex bg-white text-dark justify-content-between">
      <nav className="d-flex">
        <div className="px-2 fw-bold">
          <Link to="/">Home</Link>
        </div>

        <div className="px-2 fw-bold">
          <Link to="/live">Live Firehose</Link>
        </div>
      </nav>
    </header>
  )
}
