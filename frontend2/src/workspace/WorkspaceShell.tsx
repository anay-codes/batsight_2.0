import { useState, useEffect, useRef, type ReactNode } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import {
  Activity,
  AudioLines,
  Box,
  Compass,
  Cuboid,
  Database,
  FolderKanban,
  Home,
  Settings as SettingsIcon,
} from 'lucide-react'
import type { Health } from '../api'
import './workspace-shell.css'

interface WorkspaceShellProps {
  title: string
  health?: Health | null
  children: ReactNode
}

const navItems = [
  { to: '/workspace', label: 'Room Scanner', icon: Compass, matchPaths: ['/workspace', '/scanner'] },
  { to: '/workspace/3d', label: '3D Rooms', icon: Cuboid, matchPaths: ['/workspace/3d'] },
  { to: '/recordings', label: 'Saved Rooms', icon: Database, matchPaths: ['/recordings'] },
  { to: '/studio', label: 'Sound & Devices', icon: AudioLines, matchPaths: ['/studio'] },
  { to: '/analysis', label: 'Signal Analysis', icon: Activity, matchPaths: ['/analysis'] },
  { to: '/experiments', label: 'Experiments', icon: Box, matchPaths: ['/experiments'] },
  { to: '/projects', label: 'Projects', icon: FolderKanban, matchPaths: ['/projects'] },
  { to: '/settings', label: 'Settings', icon: SettingsIcon, matchPaths: ['/settings'] },
]

export function WorkspaceShell({ title, health, children }: WorkspaceShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const sidebarRef = useRef<HTMLElement>(null)
  const hoverZoneRef = useRef<HTMLDivElement>(null)
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const location = useLocation()

  function openSidebar() {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current)
      closeTimerRef.current = null
    }
    setSidebarOpen(true)
  }

  function scheduleSidebarClose() {
    closeTimerRef.current = setTimeout(() => {
      setSidebarOpen(false)
    }, 250)
  }

  function handleSpiderKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      setSidebarOpen((prev) => !prev)
    }
  }

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && sidebarOpen) {
        setSidebarOpen(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [sidebarOpen])

  useEffect(() => {
    return () => {
      if (closeTimerRef.current) clearTimeout(closeTimerRef.current)
    }
  }, [])

  return (
    <div className={`ws-shell ${sidebarOpen ? 'sidebar-open' : ''}`}>
      {/* Invisible left-edge hover zone for sidebar reveal */}
      <div
        ref={hoverZoneRef}
        className="ws-shell-hover-zone"
        onMouseEnter={openSidebar}
      />

      {/* Mobile/tablet dim backdrop */}
      {sidebarOpen && (
        <div
          className="ws-shell-backdrop"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Hover / Spider-toggled Sidebar */}
      <nav
        ref={sidebarRef}
        className={`ws-shell-sidebar ${sidebarOpen ? 'open' : ''}`}
        onMouseEnter={openSidebar}
        onMouseLeave={scheduleSidebarClose}
        aria-label="Workspace navigation"
      >
        <div className="ws-shell-sidebar-header">
          <div className="ws-shell-sidebar-bat-wrap" aria-hidden="true">
            <span className="ws-shell-sidebar-bat-svg" />
          </div>
          <span className="ws-shell-sidebar-brand">BATSIGHT</span>
          <span className="ws-shell-sidebar-sub">ACOUSTIC WORKSPACE</span>
        </div>

        <div className="ws-shell-nav-list">
          {navItems.map((item) => {
            const Icon = item.icon
            const isActive = item.matchPaths.some((p) =>
              p === '/projects'
                ? location.pathname === '/projects' || location.pathname.startsWith('/projects/')
                : location.pathname === p
            )
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={`ws-shell-nav-link ${isActive ? 'active' : ''}`}
                onClick={() => setSidebarOpen(false)}
              >
                <span className="ws-shell-nav-icon">
                  <Icon size={16} />
                </span>
                <span>{item.label}</span>
              </NavLink>
            )
          })}
        </div>

        <div className="ws-shell-sidebar-footer">
          <div className="ws-shell-backend-pill">
            <span className={`ws-shell-status-dot ${health ? 'online' : 'offline'}`} />
            <div>
              <b>{health ? 'Backend online' : 'API offline'}</b>
              <small>{health ? `v${health.version} · ${health.database_status}` : 'Check Settings'}</small>
            </div>
          </div>
          <Link to="/" className="ws-shell-nav-link ws-shell-nav-home" onClick={() => setSidebarOpen(false)}>
            <span className="ws-shell-nav-icon">
              <Home size={16} />
            </span>
            <span>Back to Home</span>
          </Link>
        </div>
      </nav>

      {/* Main Content Area (shifts/resizes smoothly when sidebar opens on desktop) */}
      <div className="ws-shell-main">
        {/* Cobweb + Clickable Spider (top-left, from source Image 1) */}
        <div className="ws-shell-cobweb">
          <img
            src="/assets/cobweb.svg"
            alt=""
            aria-hidden="true"
            className="ws-shell-cobweb-img"
            draggable={false}
          />
          <button
            type="button"
            className="ws-shell-spider"
            onClick={() => setSidebarOpen((prev) => !prev)}
            onKeyDown={handleSpiderKeyDown}
            aria-label="Toggle dashboard"
            aria-expanded={sidebarOpen}
            title="Toggle dashboard"
          >
            <img
              src="/assets/spider.svg"
              alt=""
              aria-hidden="true"
              className="ws-shell-spider-img"
              draggable={false}
            />
          </button>
        </div>

        {/* 4 Hanging Bats (top-right, from source Image 2, independent hover animations) */}
        <div className="ws-shell-bats" aria-hidden="true">
          <span className="ws-shell-bat-wrap bat-1">
            <img src="/assets/bat-1.svg" alt="" className="ws-shell-bat-img" draggable={false} />
          </span>
          <span className="ws-shell-bat-wrap bat-2">
            <img src="/assets/bat-2.svg" alt="" className="ws-shell-bat-img" draggable={false} />
          </span>
          <span className="ws-shell-bat-wrap bat-3">
            <img src="/assets/bat-3.svg" alt="" className="ws-shell-bat-img" draggable={false} />
          </span>
          <span className="ws-shell-bat-wrap bat-4">
            <img src="/assets/bat-4.svg" alt="" className="ws-shell-bat-img" draggable={false} />
          </span>
        </div>

        {/* Page Title */}
        <h1 className="ws-shell-title">{title}</h1>

        {/* Frosted Glass Content Panel */}
        <main className="ws-shell-panel">
          {children}
        </main>

        {/* 2-Layer City Skyline + Rooftop Cats (bottom) */}
        <div className="ws-shell-skyline" aria-hidden="true">
          <svg viewBox="0 0 1920 300" preserveAspectRatio="none" className="ws-shell-skyline-back">
            <path d="M0,300 L0,180 L30,180 L30,120 L50,120 L50,100 L70,100 L70,130 L90,130 L90,80 L110,80 L110,60 L130,60 L130,80 L150,80 L150,140 L170,140 L170,100 L190,100 L190,70 L210,70 L210,50 L230,50 L230,70 L250,70 L250,110 L270,110 L270,80 L290,80 L290,100 L310,100 L310,60 L330,60 L330,40 L350,40 L350,60 L370,60 L370,90 L390,90 L390,110 L410,110 L410,70 L430,70 L430,45 L450,45 L450,30 L470,30 L470,55 L490,55 L490,90 L510,90 L510,120 L530,120 L530,80 L550,80 L550,100 L570,100 L570,130 L590,130 L590,160 L610,160 L610,120 L630,120 L630,90 L650,90 L650,110 L670,110 L670,60 L690,60 L690,80 L710,80 L710,100 L730,100 L730,140 L750,140 L750,110 L770,110 L770,130 L790,130 L790,160 L810,160 L810,120 L830,120 L830,100 L850,100 L850,70 L870,70 L870,90 L890,90 L890,120 L910,120 L910,80 L930,80 L930,60 L950,60 L950,40 L970,40 L970,70 L990,70 L990,100 L1010,100 L1010,130 L1030,130 L1030,90 L1050,90 L1050,110 L1070,110 L1070,70 L1090,70 L1090,50 L1110,50 L1110,80 L1130,80 L1130,100 L1150,100 L1150,130 L1170,130 L1170,100 L1190,100 L1190,120 L1210,120 L1210,90 L1230,90 L1230,110 L1250,110 L1250,80 L1270,80 L1270,60 L1290,60 L1290,90 L1310,90 L1310,110 L1330,110 L1330,80 L1350,80 L1350,100 L1370,100 L1370,120 L1390,120 L1390,140 L1410,140 L1410,110 L1430,110 L1430,90 L1450,90 L1450,70 L1470,70 L1470,100 L1490,100 L1490,130 L1510,130 L1510,100 L1530,100 L1530,120 L1550,120 L1550,80 L1570,80 L1570,110 L1590,110 L1590,130 L1610,130 L1610,100 L1630,100 L1630,80 L1650,80 L1650,60 L1670,60 L1670,90 L1690,90 L1690,120 L1710,120 L1710,140 L1730,140 L1730,100 L1750,100 L1750,120 L1770,120 L1770,150 L1790,150 L1790,130 L1810,130 L1810,160 L1830,160 L1830,180 L1850,180 L1850,140 L1870,140 L1870,160 L1890,160 L1890,180 L1920,180 L1920,300Z" fill="rgba(50,65,65,0.55)" />
            <g fill="rgba(255,255,200,0.18)">
              <rect x="455" y="40" width="3" height="4" rx="0.5" />
              <rect x="462" y="40" width="3" height="4" rx="0.5" />
              <rect x="455" y="48" width="3" height="4" rx="0.5" />
              <rect x="335" y="50" width="3" height="4" rx="0.5" />
              <rect x="342" y="50" width="3" height="4" rx="0.5" />
              <rect x="955" y="50" width="3" height="4" rx="0.5" />
              <rect x="962" y="50" width="3" height="4" rx="0.5" />
              <rect x="215" y="60" width="3" height="4" rx="0.5" />
              <rect x="1095" y="60" width="3" height="4" rx="0.5" />
              <rect x="1655" y="70" width="3" height="4" rx="0.5" />
            </g>
          </svg>
          <svg viewBox="0 0 1920 200" preserveAspectRatio="none" className="ws-shell-skyline-front">
            <path d="M0,200 L0,140 L40,140 L40,100 L60,100 L60,110 L80,110 L80,80 L100,80 L100,100 L120,100 L120,60 L140,60 L140,80 L160,80 L160,120 L180,120 L180,90 L200,90 L200,100 L220,100 L220,70 L240,70 L240,90 L260,90 L260,110 L280,110 L280,130 L300,130 L300,100 L320,100 L320,80 L340,80 L340,100 L360,100 L360,120 L380,120 L380,90 L400,90 L400,70 L420,70 L420,55 L440,55 L440,80 L460,80 L460,100 L480,100 L480,120 L500,120 L500,90 L520,90 L520,110 L540,110 L540,130 L560,130 L560,100 L580,100 L580,120 L600,120 L600,80 L620,80 L620,100 L640,100 L640,130 L660,130 L660,110 L680,110 L680,90 L700,90 L700,110 L720,110 L720,130 L740,130 L740,100 L760,100 L760,80 L780,80 L780,100 L800,100 L800,120 L820,120 L820,90 L840,90 L840,110 L860,110 L860,80 L880,80 L880,100 L900,100 L900,120 L920,120 L920,100 L940,100 L940,80 L960,80 L960,100 L980,100 L980,120 L1000,120 L1000,90 L1020,90 L1020,110 L1040,110 L1040,80 L1060,80 L1060,100 L1080,100 L1080,120 L1100,120 L1100,100 L1120,100 L1120,80 L1140,80 L1140,110 L1160,110 L1160,130 L1180,130 L1180,100 L1200,100 L1200,120 L1220,120 L1220,90 L1240,90 L1240,70 L1260,70 L1260,100 L1280,100 L1280,120 L1300,120 L1300,100 L1320,100 L1320,80 L1340,80 L1340,110 L1360,110 L1360,120 L1380,120 L1380,90 L1400,90 L1400,110 L1420,110 L1420,130 L1440,130 L1440,100 L1460,100 L1460,120 L1480,120 L1480,90 L1500,90 L1500,100 L1520,100 L1520,120 L1540,120 L1540,100 L1560,100 L1560,80 L1580,80 L1580,100 L1600,100 L1600,120 L1620,120 L1620,100 L1640,100 L1640,110 L1660,110 L1660,130 L1680,130 L1680,110 L1700,110 L1700,90 L1720,90 L1720,110 L1740,110 L1740,130 L1760,130 L1760,120 L1780,120 L1780,100 L1800,100 L1800,120 L1820,120 L1820,140 L1840,140 L1840,120 L1860,120 L1860,130 L1880,130 L1880,140 L1920,140 L1920,200Z" fill="rgba(15,20,20,0.95)" />
            <g fill="rgba(255,255,180,0.6)">
              <rect x="125" y="68" width="3" height="3" rx="0.5" />
              <rect x="132" y="68" width="3" height="3" rx="0.5" />
              <rect x="125" y="76" width="3" height="3" rx="0.5" />
              <rect x="225" y="78" width="3" height="3" rx="0.5" />
              <rect x="232" y="78" width="3" height="3" rx="0.5" />
              <rect x="425" y="62" width="3" height="3" rx="0.5" />
              <rect x="432" y="62" width="3" height="3" rx="0.5" />
              <rect x="425" y="70" width="3" height="3" rx="0.5" />
              <rect x="605" y="88" width="3" height="3" rx="0.5" />
              <rect x="765" y="88" width="3" height="3" rx="0.5" />
              <rect x="772" y="88" width="3" height="3" rx="0.5" />
              <rect x="865" y="88" width="3" height="3" rx="0.5" />
              <rect x="945" y="88" width="3" height="3" rx="0.5" />
              <rect x="952" y="88" width="3" height="3" rx="0.5" />
              <rect x="1045" y="88" width="3" height="3" rx="0.5" />
              <rect x="1125" y="88" width="3" height="3" rx="0.5" />
              <rect x="1245" y="78" width="3" height="3" rx="0.5" />
              <rect x="1252" y="78" width="3" height="3" rx="0.5" />
              <rect x="1385" y="98" width="3" height="3" rx="0.5" />
              <rect x="1565" y="88" width="3" height="3" rx="0.5" />
              <rect x="1705" y="98" width="3" height="3" rx="0.5" />
            </g>
          </svg>
          <svg viewBox="0 0 1920 200" preserveAspectRatio="none" className="ws-shell-cats">
            <g transform="translate(100,52)">
              <path d="M-2,-20 L8,-5 L-12,-5Z" fill="#1a1a1a" />
              <line x1="-3" y1="-20" x2="3" y2="-28" stroke="#1a1a1a" strokeWidth="1.5" strokeLinecap="round" />
              <ellipse cx="0" cy="5" rx="8" ry="6" fill="#1a1a1a" />
              <circle cx="0" cy="-3" r="5" fill="#1a1a1a" />
              <path d="M-5,-6 L-3,-12 L-1,-6" fill="#1a1a1a" />
              <path d="M1,-6 L3,-12 L5,-6" fill="#1a1a1a" />
              <path d="M8,5 Q16,0 14,-8" fill="none" stroke="#1a1a1a" strokeWidth="2" strokeLinecap="round" />
            </g>
            <g transform="translate(1700,78)">
              <ellipse cx="0" cy="5" rx="7" ry="5" fill="#1a1a1a" />
              <circle cx="2" cy="-3" r="4.5" fill="#1a1a1a" />
              <path d="M-2,-6 L0,-12 L2,-6" fill="#1a1a1a" />
              <path d="M3,-6 L5,-12 L7,-6" fill="#1a1a1a" />
              <path d="M-7,5 Q-14,0 -12,-6" fill="none" stroke="#1a1a1a" strokeWidth="2" strokeLinecap="round" />
            </g>
            <g transform="translate(960,88) scale(0.7)">
              <ellipse cx="0" cy="4" rx="6" ry="4" fill="#1a1a1a" />
              <circle cx="0" cy="-2" r="4" fill="#1a1a1a" />
              <path d="M-3,-5 L-1,-10 L1,-5" fill="#1a1a1a" />
              <path d="M1,-5 L3,-10 L5,-5" fill="#1a1a1a" />
              <path d="M6,4 Q10,2 9,-2" fill="none" stroke="#1a1a1a" strokeWidth="1.5" strokeLinecap="round" />
            </g>
          </svg>
        </div>
      </div>
    </div>
  )
}
