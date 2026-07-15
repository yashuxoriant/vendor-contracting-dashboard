import { Container, Typography, Grid, Paper, Box } from '@mui/material'
import { Chart as ChartJS, ArcElement, CategoryScale, LinearScale, BarElement, LineElement, PointElement, Title, Tooltip, Legend } from 'chart.js'
import { Pie, Bar, Line } from 'react-chartjs-2'

ChartJS.register(
  ArcElement,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Title,
  Tooltip,
  Legend
)

// Dummy data
const spendingData = {
  labels: ['Network', 'Compute', 'Storage', 'Software', 'Services'],
  datasets: [
    {
      data: [850000, 650000, 400000, 350000, 250000],
      backgroundColor: [
        'rgba(255, 99, 132, 0.8)',
        'rgba(54, 162, 235, 0.8)',
        'rgba(255, 206, 86, 0.8)',
        'rgba(75, 192, 192, 0.8)',
        'rgba(153, 102, 255, 0.8)',
      ],
    },
  ],
}

const vendorData = {
  labels: ['CDW', 'Entity', 'Cisco Direct', 'Dell', 'IBM BP'],
  datasets: [
    {
      label: 'Total Spend ($)',
      data: [1200000, 950000, 650000, 450000, 300000],
      backgroundColor: 'rgba(54, 162, 235, 0.8)',
    },
  ],
}

const trendData = {
  labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
  datasets: [
    {
      label: 'Monthly Spending',
      data: [420000, 380000, 450000, 520000, 480000, 550000],
      borderColor: 'rgb(75, 192, 192)',
      backgroundColor: 'rgba(75, 192, 192, 0.2)',
      tension: 0.1,
    },
  ],
}

export default function DashboardPage() {
  return (
    <Container maxWidth="xl">
      <Typography variant="h4" gutterBottom>
        Analytics Dashboard
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 4 }}>
        Overview of spending patterns and vendor performance
      </Typography>

      {/* KPI Cards */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" color="text.secondary">
              Total Spend
            </Typography>
            <Typography variant="h4">$2.5M</Typography>
            <Typography variant="caption" color="success.main">
              +12% vs last quarter
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" color="text.secondary">
              BOMs Created
            </Typography>
            <Typography variant="h4">47</Typography>
            <Typography variant="caption" color="success.main">
              +8 this month
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" color="text.secondary">
              Avg BOM Time
            </Typography>
            <Typography variant="h4">18 min</Typography>
            <Typography variant="caption" color="success.main">
              -85% vs manual
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" color="text.secondary">
              Vendors
            </Typography>
            <Typography variant="h4">12</Typography>
            <Typography variant="caption">
              Active relationships
            </Typography>
          </Paper>
        </Grid>
      </Grid>

      {/* Charts */}
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Spending by Category
            </Typography>
            <Box sx={{ height: 300 }}>
              <Pie data={spendingData} options={{ maintainAspectRatio: false }} />
            </Box>
          </Paper>
        </Grid>
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Vendor Comparison
            </Typography>
            <Box sx={{ height: 300 }}>
              <Bar
                data={vendorData}
                options={{
                  maintainAspectRatio: false,
                  scales: {
                    y: {
                      beginAtZero: true,
                    },
                  },
                }}
              />
            </Box>
          </Paper>
        </Grid>
        <Grid item xs={12}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Spending Trend (6 Months)
            </Typography>
            <Box sx={{ height: 300 }}>
              <Line
                data={trendData}
                options={{
                  maintainAspectRatio: false,
                  scales: {
                    y: {
                      beginAtZero: true,
                    },
                  },
                }}
              />
            </Box>
          </Paper>
        </Grid>
      </Grid>
    </Container>
  )
}
