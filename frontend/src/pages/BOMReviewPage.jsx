import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useSelector, useDispatch } from 'react-redux'
import { saveBOM } from '../store/slices/bomSlice'
import {
  Box, Typography, Paper, Button, Grid, Chip, TextField, Alert,
  CircularProgress, Divider, Tooltip, Snackbar, IconButton,
  LinearProgress, Dialog, DialogTitle, DialogContent, DialogActions,
  Stepper, Step, StepLabel, StepContent, Select, MenuItem, FormControl, InputLabel,
} from '@mui/material'
import {
  CheckCircle, Cancel, HourglassEmpty, Lock, LockOpen,
  ArrowBack, Download, Warning, Refresh, Person, Business, Engineering,
  BuildCircle, Replay, SkipNext, Email as EmailIcon,
} from '@mui/icons-material'
import { bomService } from '../services/api'
import { pushNotification } from '../store/slices/notificationsSlice'

// Normalise Redux camelCase BOM → snake_case shape expected by this page
function normaliseBOM(b) {
  if (b.project_name) return b  // already backend shape
  return {
    ...b,
    project_name: b.project || b.name?.split(' - ')[0] || b.name || '',
    line_items: (b.lineItems || []).map(i => ({
      ...i,
      line_number:    i.lineNo,
      unit_price:     i.unitPrice,
      extended_price: i.extPrice,
    })),
    totals: { total_otc: b.totalValue || 0 },
    created_at:  b.createdAt,
    updated_at:  b.updatedAt,
    revision:    b.version || 1,
    approval_cycle: b.approval_cycle || 1,
    approvals:   b.approvals || [],
  }
}

// Sequential approval order
const PARTY_ORDER = ['buyer_it', 'seller_it', 'si']

const PARTY_META = {
  buyer_it:  { label: 'Buyer IT',  step: 'Step 1', icon: <Business sx={{ fontSize: 20 }} />,     color: '#3B82F6', bg: '#EFF6FF' },
  seller_it: { label: 'Seller IT', step: 'Step 2', icon: <Person sx={{ fontSize: 20 }} />,       color: '#10B981', bg: '#ECFDF5' },
  si:        { label: 'SI / JBR',  step: 'Step 3', icon: <Engineering sx={{ fontSize: 20 }} />,  color: '#8B5CF6', bg: '#F5F3FF' },
}

const STATUS_STYLE = {
  approved:          { label: 'Approved',          color: '#065F46', bg: '#D1FAE5', icon: <CheckCircle sx={{ fontSize: 14 }} /> },
  changes_requested: { label: 'Changes Requested', color: '#92400E', bg: '#FEF3C7', icon: <BuildCircle sx={{ fontSize: 14 }} /> },
  rejected:          { label: 'Rejected',          color: '#991B1B', bg: '#FEE2E2', icon: <Cancel sx={{ fontSize: 14 }} /> },
  pending:           { label: 'Pending',           color: '#6B7280', bg: '#F3F4F6', icon: <HourglassEmpty sx={{ fontSize: 14 }} /> },
}

// Sizing review sections each approver checks
const APPROVAL_PHASES = [
  'Size the Compute Requirements',
  'Size the Storage Requirements',
  'Size the Network Requirements',
  'Size Power and Physical Infrastructure',
]

const fmt = (v) => v != null ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v) : '—'
const fmtDate = (s) => s ? new Date(s).toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'

export default function BOMReviewPage() {
  const { bomId: urlBomId } = useParams()
  const navigate = useNavigate()
  const dispatch = useDispatch()
  const reduxBOM = useSelector(s => s.bom.currentBOM)
  const bomList  = useSelector(s => s.bom.bomList)

  // Use URL param as primary source of truth; fall back to currentBOM only when no URL param
  const bomId = urlBomId || reduxBOM?.id || null

  // Refs to read latest Redux values without them being useCallback deps (prevents re-fetch loop)
  const bomListRef  = useRef(bomList)
  const reduxBOMRef = useRef(reduxBOM)
  useEffect(() => { bomListRef.current = bomList }, [bomList])
  useEffect(() => { reduxBOMRef.current = reduxBOM }, [reduxBOM])

  const [bom, setBom] = useState(null)
  const [loading, setLoading] = useState(!!bomId)
  const [error, setError] = useState(null)
  const [approvals, setApprovals] = useState({ buyer_it: null, seller_it: null, si: null })

  // Per-party form state — extended for change requests
  const [forms, setForms] = useState({
    buyer_it: { name: '', comments: '', changeDescription: '', submitting: false, error: null },
    seller_it: { name: '', comments: '', changeDescription: '', submitting: false, error: null },
    si: { name: '', comments: '', changeDescription: '', submitting: false, error: null },
  })
  const [toast, setToast] = useState({ open: false, msg: '', severity: 'success' })
  const [actionDialog, setActionDialog] = useState(null) // { party, action: 'request_changes'|'reject' }
  const [downloading, setDownloading] = useState(false)
  // Role selector — who is the currently logged-in approver
  const [myRole, setMyRole] = useState(() => localStorage.getItem('bom_approver_role') || '')
  const [emailSending, setEmailSending] = useState(false)

  // ── Load BOM + approvals ─────────────────────────────────────────────────
  useEffect(() => {
    if (!bomId) { setLoading(false); return }
    let cancelled = false
    setLoading(true); setError(null)

    const run = async () => {
      // 1. Redux store first (seed BOMs + locally saved)
      const reduxMatch =
        bomListRef.current.find(b => b.id === bomId) ||
        (reduxBOMRef.current?.id === bomId ? reduxBOMRef.current : null)

      if (reduxMatch) {
        if (cancelled) return
        const b = normaliseBOM(reduxMatch)
        setBom(b)
        const apprMap = {}
        for (const a of b.approvals || []) apprMap[a.party] = a
        setApprovals(apprMap)
        setLoading(false)
        return
      }

      // 2. Backend API — 12 s timeout so loader never hangs forever
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), 12000)
      try {
        const data = await bomService.get(bomId, { signal: controller.signal })
        if (cancelled) return
        const b = data.bom || data
        setBom(b)
        const apprMap = {}
        for (const a of b.approvals || []) apprMap[a.party] = a
        setApprovals(apprMap)
      } catch (err) {
        if (cancelled) return
        if (err?.name === 'CanceledError' || err?.name === 'AbortError')
          setError('Request timed out. The BOM could not be loaded — check backend connectivity.')
        else if (err?.response?.status === 404)
          setError('BOM not found. It may have been deleted or the ID is incorrect.')
        else
          setError('Failed to load BOM. Please check your connection and try again.')
      } finally {
        clearTimeout(timer)
        if (!cancelled) setLoading(false)
      }
    }

    run()
    return () => { cancelled = true }
  }, [bomId])  // ← bomId only; bomList/reduxBOM via refs

  // ── Send email notification ──────────────────────────────────────────────
  const sendEmailNotification = async (subject, bodyLines) => {
    setEmailSending(true)
    try {
      // Build plain-text body with full approval thread
      const approvalThread = PARTY_ORDER.map(p => {
        const a = approvals[p]
        if (!a) return `${PARTY_META[p].label}: Pending`
        const statusLabel = a.status === 'approved' ? '✅ Approved' : a.status === 'changes_requested' ? '⚠️ Changes Requested' : '❌ Rejected'
        return `${PARTY_META[p].label}: ${statusLabel} by ${a.approved_by || '—'} on ${a.approved_at ? new Date(a.approved_at).toLocaleString() : '—'}${
          a.change_description ? `\n  Required changes: ${a.change_description}` : ''
        }${a.comments ? `\n  Comments: ${a.comments}` : ''}`
      }).join('\n')
      const fullBody = [
        ...bodyLines,
        '',
        '--- Approval Thread ---',
        approvalThread,
        '',
        `BOM: ${bom?.project_name} — ${bom?.category}`,
        `Revision: ${bom?.revision || 1}  |  Approval Cycle: ${bom?.approval_cycle || 1}`,
        `Total Value: ${bom?.totals?.total_otc != null ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(bom.totals.total_otc) : '—'}`,
      ].join('\n')
      await fetch('/api/notify/email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          to: ['yashu.singh@xoriant.com'],
          subject,
          body: fullBody,
          bom_id: bomId,
        }),
      })
      setToast(t => ({ ...t, open: true, msg: 'Email notification sent to yashu.singh@xoriant.com', severity: 'info' }))
    } catch {
      // Email is best-effort — don't block the user
    } finally {
      setEmailSending(false)
    }
  }

  // ── Approve / Request Changes / Reject ──────────────────────────────────
  const submitApproval = async (party, action) => {
    const form = forms[party]
    if (!form.name.trim()) {
      setForms(f => ({ ...f, [party]: { ...f[party], error: 'Your name is required' } }))
      return
    }
    if (action === 'request_changes' && !form.changeDescription.trim()) {
      setForms(f => ({ ...f, [party]: { ...f[party], error: 'Describe the required changes before submitting' } }))
      return
    }
    if (action === 'reject' && !form.comments.trim()) {
      setForms(f => ({ ...f, [party]: { ...f[party], error: 'Comments are required when rejecting' } }))
      return
    }

    setForms(f => ({ ...f, [party]: { ...f[party], submitting: true, error: null } }))
    try {
      // Build updated approval entry locally
      const newApproval = {
        party,
        approved_by: form.name.trim(),
        action,
        comments: form.comments.trim(),
        change_description: form.changeDescription.trim(),
        approved_at: new Date().toISOString(),
        status: action === 'approve' ? 'approved' : action === 'request_changes' ? 'changes_requested' : 'rejected',
      }

      let result
      const isLocalBOM = bomList.some(b => b.id === bomId)

      if (isLocalBOM) {
        // Apply approval locally in Redux — no API call needed
        const updatedApprovals = { ...approvals, [party]: newApproval }
        const allApproved = PARTY_ORDER.every(p => updatedApprovals[p]?.status === 'approved')
        const newStatus = allApproved ? 'approved' : action === 'reject' ? 'archived' : action === 'request_changes' ? 'draft' : bom.status
        const updatedBom = {
          ...bom,
          status: newStatus,
          approvals: Object.values(updatedApprovals).filter(Boolean),
          revision: action === 'request_changes' ? (bom.revision || 1) + 1 : bom.revision || 1,
          approval_cycle: action === 'request_changes' ? (bom.approval_cycle || 1) + 1 : bom.approval_cycle || 1,
        }
        dispatch(saveBOM(updatedBom))
        setApprovals(updatedApprovals)
        setBom(updatedBom)
        result = {
          approvals: Object.values(updatedApprovals).filter(Boolean),
          bom_status: newStatus,
          revision: updatedBom.revision,
          approval_cycle: updatedBom.approval_cycle,
          all_approved: allApproved,
          message: `${PARTY_META[party].label} ${action === 'approve' ? 'approved' : action === 'request_changes' ? 'requested changes' : 'rejected'} successfully.`,
        }
      } else {
        // Backend BOM — use API
        result = await bomService.approve(bomId, party, form.name.trim(), action, form.comments.trim(), form.changeDescription.trim())
        const updatedApprMap = {}
        for (const a of result.approvals || []) updatedApprMap[a.party] = a
        setApprovals(updatedApprMap)
        setBom(b => ({ ...b, status: result.bom_status, revision: result.revision, approval_cycle: result.approval_cycle }))
      }

      if (result.all_approved) {
        setToast({ open: true, msg: '🎉 All 3 parties approved — BOM is finalised and ready for vendor submission!', severity: 'success' })
        dispatch(pushNotification({ type: 'all_approved', title: 'BOM Fully Approved 🎉', message: `${bom?.project_name} — ${bom?.category}: all 3 parties signed off. Ready for vendor submission.`, link: `/bom-review/${bomId}` }))
        sendEmailNotification(
          `[BOM Approved] ${bom?.project_name} — ${bom?.category} — All 3 Parties Signed Off`,
          ['All three parties have approved the BOM. It is now finalised and ready for vendor submission.'],
        )
      } else if (action === 'request_changes') {
        setToast({ open: true, msg: `⚠️ ${PARTY_META[party].label} requested changes. BOM must be rebuilt. Approval cycle restarted from Buyer IT.`, severity: 'warning' })
        dispatch(pushNotification({ type: 'rebuild_required', title: `Changes Requested — ${PARTY_META[party].label}`, message: `${bom?.project_name}: rebuild required. ${form.changeDescription.trim().slice(0, 80)}${form.changeDescription.length > 80 ? '…' : ''}`, targetRole: 'BOM Creator', link: `/bom-review/${bomId}` }))
        dispatch(pushNotification({ type: 'approval_request', title: 'Approval Cycle Reset to Buyer IT', message: `${bom?.project_name} — awaiting rebuild before re-submission.`, targetRole: 'Buyer IT', link: `/bom-review/${bomId}` }))
        sendEmailNotification(
          `[BOM Changes Requested] ${bom?.project_name} — ${bom?.category} — ${PARTY_META[party].label}`,
          [`${PARTY_META[party].label} has requested changes. The BOM must be rebuilt before re-submission.`,
           `Requested by: ${form.name.trim()}`,
           `Changes required: ${form.changeDescription.trim()}`,
           `Comments: ${form.comments.trim() || '(none)'}`],
        )
      } else if (action === 'reject') {
        setToast({ open: true, msg: `BOM rejected by ${PARTY_META[party].label}. BOM has been archived.`, severity: 'error' })
        dispatch(pushNotification({ type: 'rejected', title: `BOM Rejected — ${PARTY_META[party].label}`, message: `${bom?.project_name}: BOM has been archived.`, link: `/bom-review/${bomId}` }))
        sendEmailNotification(
          `[BOM Rejected] ${bom?.project_name} — ${bom?.category} — ${PARTY_META[party].label}`,
          [`${PARTY_META[party].label} has rejected the BOM.`,
           `Rejected by: ${form.name.trim()}`,
           `Reason: ${form.comments.trim()}`],
        )
      } else {
        setToast({ open: true, msg: result.message || `${PARTY_META[party].label} approved successfully.`, severity: 'success' })
        // Notify the next party in the sequence
        const nextIdx = PARTY_ORDER.indexOf(party) + 1
        if (nextIdx < PARTY_ORDER.length) {
          const nextParty = PARTY_ORDER[nextIdx]
          dispatch(pushNotification({ type: 'approval_request', title: `Approval Required — ${PARTY_META[nextParty].label}`, message: `${bom?.project_name}: ${PARTY_META[party].label} approved. Your sign-off is next.`, targetRole: PARTY_META[nextParty].label, link: `/bom-review/${bomId}` }))
        }
        dispatch(pushNotification({ type: 'approved', title: `${PARTY_META[party].label} Approved`, message: `${bom?.project_name} — step ${PARTY_ORDER.indexOf(party) + 1} of 3 signed off.`, link: `/bom-review/${bomId}` }))
        sendEmailNotification(
          `[BOM Sign-off] ${bom?.project_name} — ${bom?.category} — ${PARTY_META[party].label} Approved`,
          [`${PARTY_META[party].label} has approved the BOM.`,
           `Approved by: ${form.name.trim()}`,
           `Comments: ${form.comments.trim() || '(none)'}`],
        )
      }
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Submission failed. Please try again.'
      setForms(f => ({ ...f, [party]: { ...f[party], error: msg } }))
    } finally {
      setForms(f => ({ ...f, [party]: { ...f[party], submitting: false } }))
      setActionDialog(null)
    }
  }

  // ── Excel download ───────────────────────────────────────────────────────
  const handleDownload = async () => {
    setDownloading(true)
    try {
      const blob = await bomService.exportExcel(bomId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `${bom?.project_name || bomId}_BOM.xlsx`
      document.body.appendChild(a); a.click(); document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch { setToast({ open: true, msg: 'Export failed — backend may be unavailable', severity: 'error' }) }
    finally { setDownloading(false) }
  }

  // ── Derived state ────────────────────────────────────────────────────────
  const approvedCount = PARTY_ORDER.filter(p => approvals[p]?.status === 'approved').length
  const changesCount  = PARTY_ORDER.filter(p => approvals[p]?.status === 'changes_requested').length
  const allApproved   = approvedCount === 3
  const isLocked      = bom?.status === 'sent_to_vendor' || bom?.status === 'archived'
  const needsRebuild  = bom?.status === 'revision_required'
  const revision      = bom?.revision || 1
  const approvalCycle = bom?.approval_cycle || 1

  // A party is actionable only if all prior parties have "approved"
  const isPartyUnlocked = (party) => {
    const idx = PARTY_ORDER.indexOf(party)
    return idx === 0 || PARTY_ORDER.slice(0, idx).every(p => approvals[p]?.status === 'approved')
  }

  // ── Render guards ────────────────────────────────────────────────────────
  if (!bomId) return (
    <Box sx={{ p: 4, textAlign: 'center' }}>
      <Warning sx={{ fontSize: 48, color: '#F59E0B', mb: 2 }} />
      <Typography variant="h6" gutterBottom>No BOM selected</Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Navigate here from the BOM Library by clicking "Review & Approve" on a BOM.
      </Typography>
      <Button variant="contained" startIcon={<ArrowBack />} onClick={() => navigate('/bom-library')}
        sx={{ bgcolor: '#D04A02', '&:hover': { bgcolor: '#A33A00' } }}>
        Go to BOM Library
      </Button>
    </Box>
  )

  if (loading) return (
    <Box sx={{ p: 4, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
      <CircularProgress sx={{ color: '#D04A02' }} />
      <Typography color="text.secondary">Loading BOM…</Typography>
    </Box>
  )

  if (error) return (
    <Box sx={{ p: 4 }}>
      <Alert severity="error" action={
        <Button size="small" onClick={load} startIcon={<Refresh />}>Retry</Button>
      }>{error}</Alert>
      <Button sx={{ mt: 2 }} startIcon={<ArrowBack />} onClick={() => navigate('/bom-library')}>Back to Library</Button>
    </Box>
  )

  return (
    <Box sx={{ bgcolor: '#FAFAFA', p: { xs: 1.5, md: 3 }, minHeight: '100vh' }}>

      {/* ── Role Selector Banner ─────────────────────────────────────────── */}
      {!myRole && (
        <Alert severity="info" sx={{ mb: 2, fontSize: '0.8rem' }}
          action={
            <FormControl size="small" sx={{ minWidth: 160 }}>
              <InputLabel sx={{ fontSize: '0.75rem' }}>I am…</InputLabel>
              <Select value={myRole} label="I am…" sx={{ fontSize: '0.75rem' }}
                onChange={e => { setMyRole(e.target.value); localStorage.setItem('bom_approver_role', e.target.value) }}>
                <MenuItem value="buyer_it" sx={{ fontSize: '0.78rem' }}>Buyer IT</MenuItem>
                <MenuItem value="seller_it" sx={{ fontSize: '0.78rem' }}>Seller IT</MenuItem>
                <MenuItem value="si" sx={{ fontSize: '0.78rem' }}>SI / JBR</MenuItem>
              </Select>
            </FormControl>
          }>
          Select your role to see your personalised approval view. You will only be able to act on your own sign-off step.
        </Alert>
      )}
      {myRole && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5, p: '6px 12px', bgcolor: PARTY_META[myRole].bg, borderRadius: 1, border: `1px solid ${PARTY_META[myRole].color}30` }}>
          <Box sx={{ color: PARTY_META[myRole].color }}>{PARTY_META[myRole].icon}</Box>
          <Typography sx={{ fontSize: '0.75rem', fontWeight: 700, color: PARTY_META[myRole].color }}>
            Viewing as: {PARTY_META[myRole].label}
          </Typography>
          <Typography sx={{ fontSize: '0.7rem', color: '#6B7280', flex: 1 }}>
            — You can only act on your own sign-off step. Other steps are read-only.
          </Typography>
          <Button size="small" onClick={() => { setMyRole(''); localStorage.removeItem('bom_approver_role') }}
            sx={{ fontSize: '0.65rem', textTransform: 'none', color: '#6B7280' }}>
            Switch role
          </Button>
        </Box>
      )}

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 2, flexWrap: 'wrap', gap: 1 }}>
        <Box>
          <Button size="small" startIcon={<ArrowBack />} onClick={() => navigate('/bom-library')}
            sx={{ mb: 0.5, color: '#6B7280', textTransform: 'none' }}>
            BOM Library
          </Button>
          <Typography sx={{ color: '#D04A02', fontWeight: 700, fontSize: '0.6rem', letterSpacing: '1px', textTransform: 'uppercase' }}>
            3-PARTY SEQUENTIAL APPROVAL WORKFLOW
          </Typography>
          <Typography sx={{ fontWeight: 700, fontSize: '1.4rem', fontFamily: '"Playfair Display", serif', color: '#1F2937', lineHeight: 1.2 }}>
            {bom?.project_name} — {bom?.category}
          </Typography>
          <Box sx={{ display: 'flex', gap: 1, mt: 0.5, flexWrap: 'wrap', alignItems: 'center' }}>
            <Chip label={`Rev ${revision}`} size="small"
              sx={{ fontSize: '0.65rem', height: 20, bgcolor: revision > 1 ? '#FEF3C7' : '#F3F4F6', color: revision > 1 ? '#92400E' : '#374151', fontWeight: 700 }} />
            {approvalCycle > 1 && (
              <Chip icon={<Replay sx={{ fontSize: 12 }} />} label={`Cycle ${approvalCycle}`} size="small"
                sx={{ fontSize: '0.65rem', height: 20, bgcolor: '#FEE2E2', color: '#991B1B', fontWeight: 700 }} />
            )}
            <Chip label={bom?.status?.replace(/_/g, ' ').toUpperCase()} size="small"
              sx={{ fontSize: '0.65rem', height: 20,
                bgcolor: allApproved ? '#D1FAE5' : needsRebuild ? '#FEF3C7' : '#F3F4F6',
                color:   allApproved ? '#065F46' : needsRebuild ? '#92400E' : '#374151',
                fontWeight: 700 }} />
            {isLocked && <Chip icon={<Lock sx={{ fontSize: 12 }} />} label="LOCKED" size="small"
              sx={{ fontSize: '0.65rem', height: 20, bgcolor: '#F3F4F6', color: '#6B7280' }} />}
          </Box>
        </Box>
        <Button variant="outlined" size="small" startIcon={downloading ? <CircularProgress size={14} /> : <Download />}
          disabled={downloading || !allApproved} onClick={handleDownload}
          sx={{ textTransform: 'none', fontSize: '0.75rem', borderColor: '#D04A02', color: '#D04A02' }}>
          {allApproved ? 'Download Excel' : 'Awaiting Final Approval'}
        </Button>
      </Box>

      {/* ── Rebuild required banner ──────────────────────────────────────── */}
      {needsRebuild && (
        <Alert severity="warning" icon={<BuildCircle />} sx={{ mb: 2, fontSize: '0.8rem' }}>
          <strong>BOM Rebuild Required.</strong> An approver has requested changes. The BOM must be rebuilt and
          resubmitted. Once resubmitted, the approval cycle restarts from <strong>Buyer IT (Step 1)</strong>.
          {PARTY_ORDER.filter(p => approvals[p]?.status === 'changes_requested').map(p => (
            <Box key={p} sx={{ mt: 0.5, pl: 1, borderLeft: '3px solid #F59E0B' }}>
              <strong>{PARTY_META[p].label}:</strong> {approvals[p]?.change_description || approvals[p]?.comments}
            </Box>
          ))}
        </Alert>
      )}

      {/* ── Cycle restart warning ────────────────────────────────────────── */}
      {approvalCycle > 1 && !needsRebuild && (
        <Alert severity="info" icon={<Replay />} sx={{ mb: 2, fontSize: '0.78rem' }}>
          This BOM is on <strong>Approval Cycle {approvalCycle}</strong> (Revision {revision}).
          {approvalCycle >= 3 && ' Consider scheduling a joint review call with all three parties to align on changes before the next rebuild.'}
        </Alert>
      )}

      {/* ── Approval progress bar ────────────────────────────────────────── */}
      <Paper sx={{ p: 2, mb: 2, borderLeft: `4px solid ${allApproved ? '#10B981' : changesCount > 0 ? '#F59E0B' : '#3B82F6'}` }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {allApproved ? <LockOpen sx={{ color: '#10B981' }} /> : needsRebuild ? <BuildCircle sx={{ color: '#F59E0B' }} /> : <Lock sx={{ color: '#3B82F6' }} />}
            <Typography sx={{ fontWeight: 700, fontSize: '0.85rem' }}>
              {allApproved
                ? '✅ All 3 parties approved — BOM is finalised'
                : needsRebuild
                ? `⚠️ Changes requested — BOM must be rebuilt before re-submission`
                : `${approvedCount} of 3 approvals received — sequential: Buyer IT → Seller IT → SI`}
            </Typography>
          </Box>
          <Typography sx={{ fontSize: '0.75rem', color: '#6B7280' }}>{approvedCount}/3</Typography>
        </Box>
        <LinearProgress variant="determinate" value={(approvedCount / 3) * 100}
          sx={{ height: 6, borderRadius: 3, bgcolor: '#F3F4F6',
            '& .MuiLinearProgress-bar': { bgcolor: allApproved ? '#10B981' : changesCount > 0 ? '#F59E0B' : '#3B82F6' } }} />
        {/* Approval phase checklist */}
        <Box sx={{ mt: 1.5, display: 'flex', flexWrap: 'wrap', gap: 0.75 }}>
          {APPROVAL_PHASES.map((phase, i) => (
            <Chip key={i} label={phase} size="small"
              sx={{ fontSize: '0.62rem', height: 18, bgcolor: '#F9FAFB', border: '1px solid #E5E7EB', color: '#6B7280' }} />
          ))}
        </Box>
        <Typography sx={{ fontSize: '0.65rem', color: '#9CA3AF', mt: 0.5 }}>
          Each approver reviews these four sizing sections. Any change request by any party resets the full cycle.
        </Typography>
      </Paper>

      {/* ── BOM Summary ──────────────────────────────────────────────────── */}
      {bom && (
        <Paper sx={{ p: 2, mb: 2 }}>
          <Typography sx={{ fontWeight: 700, fontSize: '0.8rem', mb: 1, color: '#374151' }}>BOM SUMMARY</Typography>
          <Grid container spacing={2}>
            {[
              { label: 'Line Items',    value: bom.line_items?.length || 0 },
              { label: 'Total OTC',     value: fmt(bom.totals?.total_otc) },
              { label: '3-Year TCO',    value: fmt(bom.totals?.tco_3year) },
              { label: 'Day 1 Date',    value: bom.day_one_date ? fmtDate(bom.day_one_date) : 'Not set' },
            ].map(({ label, value }) => (
              <Grid item xs={6} md={3} key={label}>
                <Typography sx={{ fontSize: '0.6rem', color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{label}</Typography>
                <Typography sx={{ fontWeight: 700, fontSize: '1rem', color: '#1F2937' }}>{value}</Typography>
              </Grid>
            ))}
          </Grid>
          {bom.line_items?.some(i => i.eol_flag) && (
            <Alert severity="warning" sx={{ mt: 1.5, fontSize: '0.75rem' }}>
              <strong>EOL/EOS Warning:</strong> {bom.line_items.filter(i => i.eol_flag).length} line item(s) are approaching end-of-life. Approvers will flag this.
            </Alert>
          )}
          {bom.notes && <Alert severity="info" icon={false} sx={{ mt: 1, fontSize: '0.75rem' }}>{bom.notes}</Alert>}
        </Paper>
      )}

      {/* ── Sequential Approval Cards ─────────────────────────────────────── */}
      <Grid container spacing={2}>
        {PARTY_ORDER.map((party, idx) => {
          const meta        = PARTY_META[party]
          const appr        = approvals[party]
          const apprStatus  = appr?.status || 'pending'
          const ss          = STATUS_STYLE[apprStatus] || STATUS_STYLE.pending
          const form        = forms[party]
          const unlocked    = isPartyUnlocked(party)
          const isDecided   = ['approved', 'changes_requested', 'rejected'].includes(apprStatus)
          const isPending   = apprStatus === 'pending'
          const isChanges   = apprStatus === 'changes_requested'
          const priorLabel  = idx > 0 ? PARTY_META[PARTY_ORDER[idx - 1]].label : null
          // Role-specific: if a role is selected, only that party can act; others are view-only
          const isMyCard    = !myRole || myRole === party
          const isViewOnly  = myRole && myRole !== party

          return (
            <Grid item xs={12} md={4} key={party}>
              <Paper sx={{
                p: 2, height: '100%',
                borderTop: `3px solid ${unlocked ? meta.color : '#E5E7EB'}`,
                opacity: unlocked ? 1 : 0.7,
                position: 'relative',
                outline: isMyCard && isPending && unlocked ? `2px solid ${meta.color}` : 'none',
              }}>
                {/* View-only badge for other parties */}
                {isViewOnly && (
                  <Chip label="View only" size="small"
                    sx={{ position: 'absolute', top: 8, right: 8, fontSize: '0.55rem', height: 18, bgcolor: '#F3F4F6', color: '#9CA3AF' }} />
                )}
                {/* Step label */}
                <Typography sx={{ fontSize: '0.6rem', color: unlocked ? meta.color : '#9CA3AF', fontWeight: 700,
                  letterSpacing: '0.5px', textTransform: 'uppercase', mb: 0.5 }}>
                  {meta.step} {idx > 0 && !unlocked && `— Waiting for ${priorLabel}`}
                </Typography>

                {/* Card header */}
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Box sx={{ color: unlocked ? meta.color : '#9CA3AF' }}>{meta.icon}</Box>
                    <Typography sx={{ fontWeight: 700, fontSize: '0.9rem', color: '#1F2937' }}>{meta.label}</Typography>
                  </Box>
                  <Chip icon={ss.icon} label={ss.label} size="small"
                    sx={{ bgcolor: ss.bg, color: ss.color, fontWeight: 700, fontSize: '0.65rem', height: 22,
                      '& .MuiChip-icon': { color: ss.color } }} />
                </Box>

                {/* Already decided: show outcome */}
                {isDecided && (
                  <Box sx={{ p: 1.5, bgcolor: ss.bg, borderRadius: 1, mb: 1 }}>
                    <Typography sx={{ fontSize: '0.75rem', fontWeight: 600, color: ss.color }}>
                      {apprStatus === 'approved' ? '✓ Approved' : apprStatus === 'changes_requested' ? '⚠ Changes Requested' : '✗ Rejected'} by {appr.approved_by}
                    </Typography>
                    <Typography sx={{ fontSize: '0.68rem', color: '#6B7280', mt: 0.3 }}>{fmtDate(appr.approved_at)}</Typography>
                    {appr.change_description && (
                      <Typography sx={{ fontSize: '0.72rem', color: '#92400E', mt: 0.5, fontWeight: 600 }}>
                        Required changes: {appr.change_description}
                      </Typography>
                    )}
                    {appr.comments && !appr.change_description && (
                      <Typography sx={{ fontSize: '0.72rem', color: '#374151', mt: 0.5, fontStyle: 'italic' }}>"{appr.comments}"</Typography>
                    )}
                    {isChanges && (
                      <Alert severity="warning" sx={{ mt: 1, fontSize: '0.68rem', py: 0 }}>
                        Approval cycle restarted from Step 1 (Buyer IT) after rebuild.
                      </Alert>
                    )}
                  </Box>
                )}

                {/* Locked — waiting for prior party */}
                {!unlocked && isPending && (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: 1.5, bgcolor: '#F9FAFB', borderRadius: 1 }}>
                    <Lock sx={{ fontSize: 16, color: '#9CA3AF' }} />
                    <Typography sx={{ fontSize: '0.75rem', color: '#6B7280' }}>
                      Locked until <strong>{priorLabel}</strong> approves
                    </Typography>
                  </Box>
                )}

                {/* Pending and unlocked — show action form (only for the user's own card) */}
                {unlocked && isPending && !isLocked && !needsRebuild && isMyCard && (
                  <Box>
                    <TextField size="small" fullWidth label="Your name *" value={form.name}
                      onChange={e => setForms(f => ({ ...f, [party]: { ...f[party], name: e.target.value, error: null } }))}
                      sx={{ mb: 1, '& .MuiInputBase-input': { fontSize: '0.8rem' } }} inputProps={{ maxLength: 80 }} />
                    <TextField size="small" fullWidth multiline rows={2} label="Comments (optional)"
                      value={form.comments}
                      onChange={e => setForms(f => ({ ...f, [party]: { ...f[party], comments: e.target.value, error: null } }))}
                      sx={{ mb: 1, '& .MuiInputBase-input': { fontSize: '0.78rem' } }} inputProps={{ maxLength: 500 }} />
                    {form.error && <Alert severity="error" sx={{ mb: 1, py: 0, fontSize: '0.72rem' }}>{form.error}</Alert>}
                    <Box sx={{ display: 'flex', gap: 1, flexDirection: 'column' }}>
                      <Button fullWidth variant="contained" size="small"
                        disabled={form.submitting || !form.name.trim()}
                        onClick={() => submitApproval(party, 'approve')}
                        startIcon={form.submitting ? <CircularProgress size={12} /> : <CheckCircle sx={{ fontSize: 14 }} />}
                        sx={{ bgcolor: meta.color, '&:hover': { filter: 'brightness(0.9)' }, textTransform: 'none', fontSize: '0.75rem', fontWeight: 700 }}>
                        Approve
                      </Button>
                      <Button fullWidth variant="outlined" size="small" color="warning"
                        disabled={form.submitting}
                        onClick={() => setActionDialog({ party, action: 'request_changes' })}
                        startIcon={<BuildCircle sx={{ fontSize: 14 }} />}
                        sx={{ textTransform: 'none', fontSize: '0.75rem', borderColor: '#F59E0B', color: '#92400E' }}>
                        Request Changes
                      </Button>
                    </Box>
                  </Box>
                )}

                {needsRebuild && isPending && (
                  <Alert severity="warning" sx={{ fontSize: '0.72rem', mt: 0.5 }}>
                    Awaiting BOM rebuild before this step can proceed.
                  </Alert>
                )}

                {/* View-only: show message when another party's pending unlocked card */}
                {unlocked && isPending && !isLocked && !needsRebuild && isViewOnly && (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: 1.5, bgcolor: '#F9FAFB', borderRadius: 1 }}>
                    <Person sx={{ fontSize: 16, color: '#9CA3AF' }} />
                    <Typography sx={{ fontSize: '0.72rem', color: '#6B7280' }}>
                      Awaiting {meta.label} sign-off. You can view this step but cannot act on it.
                    </Typography>
                  </Box>
                )}
              </Paper>
            </Grid>
          )
        })}
      </Grid>

      {/* ── All approved banner ───────────────────────────────────────────── */}
      {allApproved && (
        <Alert severity="success" sx={{ mt: 2, fontSize: '0.8rem' }}
          action={
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button size="small" onClick={() => sendEmailNotification(
                `[BOM Fully Approved] ${bom?.project_name} — ${bom?.category}`,
                ['All three parties have approved the BOM. It is finalised and ready for vendor submission.'],
              )} startIcon={<EmailIcon sx={{ fontSize: 14 }} />} disabled={emailSending}
                sx={{ color: '#065F46', fontWeight: 700, textTransform: 'none' }}>
                {emailSending ? 'Sending…' : 'Email Summary'}
              </Button>
              <Button size="small" onClick={handleDownload} startIcon={<Download />}
                sx={{ color: '#065F46', fontWeight: 700, textTransform: 'none' }}>Download Excel</Button>
            </Box>
          }>
          <strong>BOM fully approved.</strong> All 3 parties have signed off. Email the summary or download the Excel and submit to vendors.
        </Alert>
      )}

      {/* ── Request Changes dialog ────────────────────────────────────────── */}
      <Dialog open={actionDialog?.action === 'request_changes'} onClose={() => setActionDialog(null)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontSize: '1rem' }}>
          Request Changes — {actionDialog ? PARTY_META[actionDialog.party]?.label : ''}
        </DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2, fontSize: '0.78rem' }}>
            Requesting changes will <strong>reset the entire approval cycle</strong> back to Step 1 (Buyer IT).
            The BOM must be rebuilt before re-submission.
          </Alert>
          <Typography sx={{ fontSize: '0.8rem', color: '#374151', mb: 1.5 }}>
            Describe the required changes in detail so the BOM creator knows exactly what to fix:
          </Typography>
          {actionDialog && (
            <TextField fullWidth multiline rows={4} label="Required changes *" size="small"
              value={forms[actionDialog.party]?.changeDescription || ''}
              onChange={e => setForms(f => ({ ...f, [actionDialog.party]: { ...f[actionDialog.party], changeDescription: e.target.value } }))}
              placeholder="e.g. Compute sizing needs 20% more headroom; storage tier 1 IOPS underspecified for the ERP workload; UPS kVA calculation incorrect"
              inputProps={{ maxLength: 1000 }}
              sx={{ '& .MuiInputBase-input': { fontSize: '0.8rem' } }} />
          )}
          <Typography sx={{ fontSize: '0.65rem', color: '#9CA3AF', mt: 0.5 }}>
            Sizing review areas: Compute · Storage · Network · Power & Physical
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button size="small" onClick={() => setActionDialog(null)} sx={{ textTransform: 'none' }}>Cancel</Button>
          <Button size="small" color="warning" variant="contained"
            disabled={!actionDialog || !forms[actionDialog.party]?.changeDescription?.trim()}
            onClick={() => submitApproval(actionDialog.party, 'request_changes')}
            sx={{ textTransform: 'none', bgcolor: '#F59E0B', color: '#fff', '&:hover': { bgcolor: '#D97706' } }}>
            Submit — Reset Approval Cycle
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── Toast notifications ───────────────────────────────────────────── */}
      <Snackbar open={toast.open} autoHideDuration={6000} onClose={() => setToast(t => ({ ...t, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        <Alert severity={toast.severity} onClose={() => setToast(t => ({ ...t, open: false }))} sx={{ fontSize: '0.8rem' }}>
          {toast.msg}
        </Alert>
      </Snackbar>
    </Box>
  )
}
