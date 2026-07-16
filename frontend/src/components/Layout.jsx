import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useSelector, useDispatch } from 'react-redux'
import { Box, Tooltip, IconButton, Chip, Button, Typography, Divider, Badge, Drawer, List, ListItem, ListItemText } from '@mui/material'
import {
  Dashboard as DashboardIcon,
  CompareArrows as CompareIcon,
  Receipt as ReceiptIcon,
  Build as BuildIcon,
  AutoAwesome as ChatIcon,
  LibraryBooks as LibraryIcon,
  FileDownload, Refresh, ChevronLeft, ChevronRight,
  NotificationsOutlined, NotificationsActive, Close, DoneAll, DeleteSweep,
} from '@mui/icons-material'
import { markRead, markAllRead, deleteNotification, clearAll, pushNotification, NOTIF_TYPES } from '../store/slices/notificationsSlice'

const NAV_W = 220
const NAV_C = 52

const menuItems = [
  { text: 'Overview', icon: <DashboardIcon sx={{ fontSize: 17 }} />, path: '/overview' },
  { text: 'BOM Library', icon: <LibraryIcon sx={{ fontSize: 17 }} />, path: '/bom-library' },
  { text: 'AI BOM Assistant', icon: <ChatIcon sx={{ fontSize: 17 }} />, path: '/chat' },
  { text: 'Vendor Price Selector', icon: <CompareIcon sx={{ fontSize: 17 }} />, path: '/vendor-selector' },
  { text: 'Quote Extractor', icon: <ReceiptIcon sx={{ fontSize: 17 }} />, path: '/quote-extractor' },
  { text: 'RFQ Builder', icon: <BuildIcon sx={{ fontSize: 17 }} />, path: '/rfq-builder' },
]

const ROLES = ['All Users', 'Buyer IT', 'Seller IT', 'SI / JBR', 'BOM Creator']

// Broadcast message composer panel (shown at bottom of notification drawer)
function BroadcastComposer({ dispatch }) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [message, setMessage] = useState('')
  const [targetRole, setTargetRole] = useState('All Users')
  const [notifType, setNotifType] = useState('info')

  const typeOptions = [
    { value: 'info',             label: 'Info' },
    { value: 'approval_request', label: 'Approval Request' },
    { value: 'bom_ready',        label: 'BOM Ready' },
    { value: 'rebuild_required', label: 'Rebuild Required' },
    { value: 'approved',         label: 'Approved' },
    { value: 'changes_requested',label: 'Changes Requested' },
  ]

  const handleSend = () => {
    if (!title.trim()) return
    dispatch(pushNotification({
      type: notifType,
      title: title.trim(),
      message: message.trim(),
      targetRole: targetRole !== 'All Users' ? targetRole : undefined,
      broadcast: true,
    }))
    setTitle(''); setMessage(''); setOpen(false)
  }

  return (
    <Box sx={{ borderTop: '1px solid #E5E7EB', bgcolor: 'white' }}>
      {!open ? (
        <Box sx={{ px: 2, py: 1 }}>
          <Button fullWidth size="small" startIcon={<NotificationsActive sx={{ fontSize: 14 }} />}
            onClick={() => setOpen(true)}
            sx={{ textTransform: 'none', fontSize: '0.72rem', fontWeight: 700,
              color: '#D04A02', border: '1px dashed #FBBF9F', bgcolor: '#FFF7F0',
              '&:hover': { bgcolor: '#FEE8D8' } }}>
            Broadcast a notification
          </Button>
        </Box>
      ) : (
        <Box sx={{ px: 2, py: 1.5 }}>
          <Typography sx={{ fontSize: '0.7rem', fontWeight: 700, color: '#1F2937', mb: 1 }}>
            Broadcast notification
          </Typography>
          <Box component="input" placeholder="Title *" value={title} onChange={e => setTitle(e.target.value)}
            sx={{ width: '100%', border: '1px solid #E5E7EB', borderRadius: 1, p: '6px 10px', fontSize: '0.75rem',
              mb: 0.75, outline: 'none', '&:focus': { borderColor: '#D04A02' }, boxSizing: 'border-box' }} />
          <Box component="textarea" placeholder="Message (optional)" value={message} onChange={e => setMessage(e.target.value)}
            rows={2}
            sx={{ width: '100%', border: '1px solid #E5E7EB', borderRadius: 1, p: '6px 10px', fontSize: '0.73rem',
              mb: 0.75, outline: 'none', resize: 'none', fontFamily: 'inherit',
              '&:focus': { borderColor: '#D04A02' }, boxSizing: 'border-box' }} />
          <Box sx={{ display: 'flex', gap: 0.75, mb: 1 }}>
            <Box component="select" value={notifType} onChange={e => setNotifType(e.target.value)}
              sx={{ flex: 1, border: '1px solid #E5E7EB', borderRadius: 1, p: '4px 6px', fontSize: '0.72rem',
                outline: 'none', bgcolor: 'white', '&:focus': { borderColor: '#D04A02' } }}>
              {typeOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Box>
            <Box component="select" value={targetRole} onChange={e => setTargetRole(e.target.value)}
              sx={{ flex: 1, border: '1px solid #E5E7EB', borderRadius: 1, p: '4px 6px', fontSize: '0.72rem',
                outline: 'none', bgcolor: 'white', '&:focus': { borderColor: '#D04A02' } }}>
              {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
            </Box>
          </Box>
          <Box sx={{ display: 'flex', gap: 0.75 }}>
            <Button fullWidth size="small" onClick={() => setOpen(false)}
              sx={{ textTransform: 'none', fontSize: '0.7rem', color: '#6B7280', border: '1px solid #E5E7EB' }}>
              Cancel
            </Button>
            <Button fullWidth size="small" variant="contained" disabled={!title.trim()} onClick={handleSend}
              sx={{ textTransform: 'none', fontSize: '0.7rem', fontWeight: 700, bgcolor: '#D04A02', '&:hover': { bgcolor: '#A33A00' } }}>
              Send Broadcast
            </Button>
          </Box>
        </Box>
      )}
    </Box>
  )
}

export default function Layout({ children }) {
  const navigate = useNavigate()
  const location = useLocation()
  const dispatch = useDispatch()
  const [collapsed, setCollapsed] = useState(false)
  const [notifOpen, setNotifOpen] = useState(false)
  const { items: notifications, unreadCount } = useSelector(s => s.notifications)

  const fmtTime = (iso) => {
    const d = new Date(iso)
    const now = new Date()
    const diffMs = now - d
    const diffMin = Math.floor(diffMs / 60000)
    if (diffMin < 1) return 'just now'
    if (diffMin < 60) return `${diffMin}m ago`
    if (diffMin < 1440) return `${Math.floor(diffMin / 60)}h ago`
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  return (
    <Box sx={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>

      {/* ── Light Sidebar ── */}
      <Box sx={{
        width: collapsed ? NAV_C : NAV_W,
        flexShrink: 0,
        bgcolor: '#FFFFFF',
        borderRight: '1px solid #E5E7EB',
        display: 'flex',
        flexDirection: 'column',
        transition: 'width 0.2s ease',
        overflow: 'hidden',
        position: 'relative',
        zIndex: 100,
      }}>

        {/* PwC Logo */}
        <Box sx={{
          display: 'flex', alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'flex-start',
          gap: collapsed ? 0 : 1.25,
          px: collapsed ? 0 : 1.5, py: 1.25,
          minHeight: 56, flexShrink: 0,
          borderBottom: '1px solid #F3F4F6',
        }}>
          <Typography
            onClick={() => navigate('/overview')}
            sx={{
              fontFamily: '"Playfair Display", Georgia, serif',
              fontWeight: 800, color: '#D04A02',
              fontSize: collapsed ? '1.1rem' : '1.65rem',
              letterSpacing: '-1px', lineHeight: 1, cursor: 'pointer',
              flexShrink: 0, whiteSpace: 'nowrap',
            }}
          >
            {collapsed ? 'pw' : 'pwc'}
          </Typography>
          {!collapsed && (
            <>
              <Box sx={{ width: 1, height: 26, bgcolor: '#E5E7EB', flexShrink: 0 }} />
              <Box sx={{ overflow: 'hidden', flex: 1 }}>
                <Typography sx={{ fontWeight: 700, fontSize: '0.7rem', color: '#1F2937', lineHeight: 1.2, whiteSpace: 'nowrap' }}>
                  IT Contracting
                </Typography>
                <Typography sx={{ fontSize: '0.58rem', color: '#9CA3AF', whiteSpace: 'nowrap' }}>
                  Intelligence Platform
                </Typography>
              </Box>
            </>
          )}
        </Box>

        {/* Nav section label */}
        {!collapsed && (
          <Box sx={{ px: 1.75, pt: 1.25, pb: 0.5 }}>
            <Typography sx={{ fontSize: '0.55rem', fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.8px' }}>
              Navigation
            </Typography>
          </Box>
        )}

        {/* Nav items */}
        <Box sx={{ flex: 1, pb: 1, overflowY: 'auto', overflowX: 'hidden' }}>
          {menuItems.map(item => {
            const active = location.pathname === item.path || (location.pathname === '/' && item.path === '/overview')
            const el = (
              <Box
                key={item.path}
                onClick={() => navigate(item.path)}
                sx={{
                  display: 'flex', alignItems: 'center',
                  gap: 1.25,
                  px: collapsed ? 0 : 1.5, py: 0.85,
                  mx: 0.6, mb: 0.2, borderRadius: '6px',
                  cursor: 'pointer',
                  justifyContent: collapsed ? 'center' : 'flex-start',
                  bgcolor: active ? '#FDF3ED' : 'transparent',
                  borderLeft: !collapsed && active ? '3px solid #D04A02' : '3px solid transparent',
                  '&:hover': { bgcolor: active ? '#FDF3ED' : '#F9FAFB' },
                  transition: 'background 0.12s',
                }}
              >
                <Box sx={{ color: active ? '#D04A02' : '#6B7280', display: 'flex', flexShrink: 0, minWidth: 17 }}>
                  {item.icon}
                </Box>
                {!collapsed && (
                  <Typography sx={{
                    fontSize: '0.75rem', fontWeight: active ? 700 : 500,
                    color: active ? '#D04A02' : '#374151',
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                    lineHeight: 1.3,
                  }}>
                    {item.text}
                  </Typography>
                )}
              </Box>
            )
            return collapsed
              ? <Tooltip key={item.path} title={item.text} placement="right" arrow>{el}</Tooltip>
              : el
          })}
        </Box>

        {/* Bottom: status + collapse */}
        <Box sx={{ borderTop: '1px solid #F3F4F6', p: 1 }}>
          {!collapsed && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.75, px: 0.5 }}>
              <Box sx={{
                width: 6, height: 6, bgcolor: '#10B981', borderRadius: '50%', flexShrink: 0,
                animation: 'pulse 2s infinite',
                '@keyframes pulse': { '0%,100%': { opacity: 1 }, '50%': { opacity: 0.4 } },
              }} />
              <Typography sx={{ fontSize: '0.58rem', color: '#9CA3AF' }}>48 Records · Demo Mode</Typography>
            </Box>
          )}
          <Tooltip title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} placement="right" arrow>
            <IconButton
              size="small"
              onClick={() => setCollapsed(!collapsed)}
              sx={{ width: '100%', borderRadius: '6px', py: 0.5, color: '#9CA3AF', '&:hover': { bgcolor: '#F3F4F6', color: '#374151' } }}
            >
              {collapsed ? <ChevronRight sx={{ fontSize: 17 }} /> : <ChevronLeft sx={{ fontSize: 17 }} />}
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {/* ── Right: topbar + content ── */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0, bgcolor: '#FAFAFA' }}>

        {/* Slim top bar */}
        <Box sx={{
          height: 44, flexShrink: 0,
          bgcolor: 'white', borderBottom: '1px solid #E5E7EB',
          display: 'flex', alignItems: 'center', px: 2, gap: 1.5,
        }}>
          <Typography sx={{ fontWeight: 600, fontSize: '0.78rem', color: '#6B7280', flex: 1 }}>
            Vendor Benchmarking &amp; Sourcing Platform
          </Typography>
          <Chip
            label="● Live Demo"
            size="small"
            sx={{ bgcolor: '#D1FAE5', color: '#065F46', fontWeight: 700, fontSize: '0.6rem', height: 22, '& .MuiChip-label': { px: 1 } }}
          />
          {/* Notification bell */}
          <Tooltip title={unreadCount > 0 ? `${unreadCount} unread notifications` : 'Notifications'}>
            <IconButton size="small" onClick={() => setNotifOpen(true)}
              sx={{ color: unreadCount > 0 ? '#D04A02' : '#9CA3AF', '&:hover': { color: '#D04A02' } }}>
              <Badge badgeContent={unreadCount || null} max={9}
                sx={{ '& .MuiBadge-badge': { bgcolor: '#D04A02', color: 'white', fontSize: '0.55rem', minWidth: 16, height: 16, p: '0 3px' } }}>
                {unreadCount > 0
                  ? <NotificationsActive sx={{ fontSize: 18 }} />
                  : <NotificationsOutlined sx={{ fontSize: 18 }} />}
              </Badge>
            </IconButton>
          </Tooltip>
          <Button size="small" variant="outlined" startIcon={<Refresh sx={{ fontSize: '13px !important' }} />}
            sx={{ textTransform: 'none', fontSize: '0.7rem', fontWeight: 600, color: '#374151', borderColor: '#E5E7EB', py: 0.3, '&:hover': { borderColor: '#D04A02', color: '#D04A02' } }}>
            Refresh
          </Button>
          <Button size="small" variant="contained" startIcon={<FileDownload sx={{ fontSize: '13px !important' }} />}
            sx={{ textTransform: 'none', fontSize: '0.7rem', fontWeight: 600, bgcolor: '#D04A02', py: 0.3, '&:hover': { bgcolor: '#A33A00' } }}>
            Export
          </Button>
        </Box>

        {/* Page content */}
        <Box component="main" sx={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
          {children}
        </Box>
      </Box>

      {/* ── Notification drawer ──────────────────────────────────────────── */}
      <Drawer anchor="right" open={notifOpen} onClose={() => setNotifOpen(false)}
        PaperProps={{ sx: { width: 360, bgcolor: '#FAFAFA' } }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

          {/* Drawer header */}
          <Box sx={{ display: 'flex', alignItems: 'center', px: 2, py: 1.5, bgcolor: 'white', borderBottom: '1px solid #E5E7EB' }}>
            <NotificationsActive sx={{ fontSize: 18, color: '#D04A02', mr: 1 }} />
            <Typography sx={{ fontWeight: 700, fontSize: '0.9rem', color: '#1F2937', flex: 1 }}>
              Notifications
            </Typography>
            {unreadCount > 0 && (
              <Chip label={`${unreadCount} new`} size="small"
                sx={{ bgcolor: '#FFF7F0', color: '#D04A02', fontWeight: 700, fontSize: '0.6rem', height: 20, mr: 1 }} />
            )}
            <Tooltip title="Mark all read">
              <IconButton size="small" onClick={() => dispatch(markAllRead())} sx={{ color: '#9CA3AF', '&:hover': { color: '#D04A02' } }}>
                <DoneAll sx={{ fontSize: 16 }} />
              </IconButton>
            </Tooltip>
            <Tooltip title="Clear all">
              <IconButton size="small" onClick={() => dispatch(clearAll())} sx={{ color: '#9CA3AF', '&:hover': { color: '#EF4444' } }}>
                <DeleteSweep sx={{ fontSize: 16 }} />
              </IconButton>
            </Tooltip>
            <IconButton size="small" onClick={() => setNotifOpen(false)} sx={{ ml: 0.5, color: '#6B7280' }}>
              <Close sx={{ fontSize: 16 }} />
            </IconButton>
          </Box>

          {/* Notification list */}
          <Box sx={{ flex: 1, overflowY: 'auto', p: 1 }}>
            {notifications.length === 0 ? (
              <Box sx={{ textAlign: 'center', pt: 6 }}>
                <NotificationsOutlined sx={{ fontSize: 40, color: '#E5E7EB', mb: 1 }} />
                <Typography sx={{ fontSize: '0.8rem', color: '#9CA3AF' }}>No notifications yet</Typography>
                <Typography sx={{ fontSize: '0.72rem', color: '#D1D5DB', mt: 0.5 }}>
                  BOM approvals, status changes and broadcasts will appear here
                </Typography>
              </Box>
            ) : (
              notifications.map(n => {
                const cfg = NOTIF_TYPES[n.type] || NOTIF_TYPES.info
                return (
                  <Box key={n.id}
                    onClick={() => { dispatch(markRead(n.id)); if (n.link) navigate(n.link) }}
                    sx={{
                      display: 'flex', gap: 1, p: '10px 12px', mb: 0.75, borderRadius: '8px',
                      bgcolor: n.read ? 'white' : cfg.bg,
                      border: `1px solid ${n.read ? '#F3F4F6' : cfg.color + '30'}`,
                      cursor: n.link ? 'pointer' : 'default',
                      '&:hover': { bgcolor: '#F9FAFB' },
                      position: 'relative',
                    }}>
                    {/* Icon */}
                    <Box sx={{ fontSize: '1.1rem', lineHeight: 1.4, flexShrink: 0 }}>{cfg.icon}</Box>

                    {/* Body */}
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 0.5 }}>
                        <Typography sx={{ fontSize: '0.74rem', fontWeight: n.read ? 600 : 700, color: '#1F2937', lineHeight: 1.3, flex: 1 }}>
                          {n.title}
                        </Typography>
                        <Typography sx={{ fontSize: '0.58rem', color: '#9CA3AF', flexShrink: 0, mt: '2px' }}>
                          {fmtTime(n.timestamp)}
                        </Typography>
                      </Box>
                      {n.message && (
                        <Typography sx={{ fontSize: '0.68rem', color: '#6B7280', mt: 0.3, lineHeight: 1.4 }}>
                          {n.message}
                        </Typography>
                      )}
                      {n.targetRole && (
                        <Chip label={`For: ${n.targetRole}`} size="small"
                          sx={{ mt: 0.5, fontSize: '0.55rem', height: 16, bgcolor: cfg.bg, color: cfg.color, fontWeight: 700 }} />
                      )}
                      {n.link && (
                        <Typography sx={{ fontSize: '0.62rem', color: cfg.color, fontWeight: 700, mt: 0.5 }}>
                          Click to view →
                        </Typography>
                      )}
                    </Box>

                    {/* Unread dot */}
                    {!n.read && (
                      <Box sx={{ width: 7, height: 7, borderRadius: '50%', bgcolor: cfg.color, flexShrink: 0, mt: '5px' }} />
                    )}

                    {/* Delete */}
                    <IconButton size="small"
                      onClick={e => { e.stopPropagation(); dispatch(deleteNotification(n.id)) }}
                      sx={{ position: 'absolute', top: 4, right: 4, opacity: 0, p: 0.2,
                        color: '#9CA3AF', '&:hover': { color: '#EF4444', bgcolor: '#FEE2E2' },
                        '.MuiBox-root:hover > &': { opacity: 1 } }}>
                      <Close sx={{ fontSize: 10 }} />
                    </IconButton>
                  </Box>
                )
              })
            )}
          </Box>

          {/* Drawer footer — broadcast composer */}
          <BroadcastComposer dispatch={dispatch} />
        </Box>
      </Drawer>
    </Box>
  )
}
