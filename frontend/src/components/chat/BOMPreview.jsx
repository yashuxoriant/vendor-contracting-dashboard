import { useSelector } from 'react-redux'
import {
  Paper,
  Box,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  LinearProgress,
  Button,
  Divider,
} from '@mui/material'
import { Download as DownloadIcon } from '@mui/icons-material'

export default function BOMPreview() {
  const partialBOM = useSelector((state) => state.chat.partialBOM)
  const context = useSelector((state) => state.chat.context)

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
    }).format(value)
  }

  if (!partialBOM) {
    return (
      <Paper sx={{ height: '100%', p: 3 }}>
        <Typography variant="h6" gutterBottom>
          BOM Preview
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Your BOM will appear here as we build it together...
        </Typography>
        <Box sx={{ mt: 4 }}>
          <Typography variant="caption" color="text.secondary">
            Progress: {context.progress}%
          </Typography>
          <LinearProgress variant="determinate" value={context.progress} sx={{ mt: 1 }} />
        </Box>
      </Paper>
    )
  }

  return (
    <Paper sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
        <Typography variant="h6">BOM Preview</Typography>
        <Typography variant="caption" color="text.secondary">
          Generated from your answers
        </Typography>
      </Box>

      <Box sx={{ flexGrow: 1, overflow: 'auto', p: 2 }}>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>#</TableCell>
                <TableCell>Description</TableCell>
                <TableCell align="right">Qty</TableCell>
                <TableCell align="right">Unit Price</TableCell>
                <TableCell align="right">Total</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {partialBOM.line_items.map((item) => (
                <TableRow key={item.line_number}>
                  <TableCell>{item.line_number}</TableCell>
                  <TableCell>{item.description}</TableCell>
                  <TableCell align="right">{item.qty}</TableCell>
                  <TableCell align="right">{formatCurrency(item.unit_price)}</TableCell>
                  <TableCell align="right">{formatCurrency(item.extended_price)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>

        <Divider sx={{ my: 2 }} />

        <Box sx={{ mt: 2 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="body2">Hardware:</Typography>
            <Typography variant="body2" fontWeight="bold">
              {formatCurrency(partialBOM.totals.hardware)}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="body2">Software:</Typography>
            <Typography variant="body2" fontWeight="bold">
              {formatCurrency(partialBOM.totals.software)}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="body2">Services:</Typography>
            <Typography variant="body2" fontWeight="bold">
              {formatCurrency(partialBOM.totals.services)}
            </Typography>
          </Box>
          <Divider sx={{ my: 1 }} />
          <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
            <Typography variant="h6">Total:</Typography>
            <Typography variant="h6" color="primary">
              {formatCurrency(partialBOM.totals.total_otc)}
            </Typography>
          </Box>
        </Box>
      </Box>

      <Box sx={{ p: 2, borderTop: 1, borderColor: 'divider' }}>
        <Button
          fullWidth
          variant="contained"
          startIcon={<DownloadIcon />}
          onClick={() => alert('Export functionality coming soon!')}
        >
          Export to Excel
        </Button>
      </Box>
    </Paper>
  )
}
