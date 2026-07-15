import { createTheme } from '@mui/material/styles'

// PwC Brand Colors (matching index.html exactly)
const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#D04A02', // --or (PwC Orange)
      light: '#E8703A', // --orm
      dark: '#A33A00', // --ord
      contrastText: '#FFFFFF',
    },
    secondary: {
      main: '#1F2937', // --ink (dark gray)
      light: '#374151', // --ink2
      dark: '#111827',
      contrastText: '#FFFFFF',
    },
    success: {
      main: '#10B981', // --gn
      light: '#D1FAE5', // --gnl
      dark: '#065F46', // --gnd
    },
    info: {
      main: '#3B82F6', // --bl
      light: '#DBEAFE', // --bll
      dark: '#1E40AF', // --bld
    },
    warning: {
      main: '#F59E0B', // --am
      light: '#FEF3C7', // --aml
      dark: '#92400E', // --amd
    },
    error: {
      main: '#EF4444', // --rd
      light: '#FEE2E2', // --rdl
      dark: '#991B1B', // --rdd
    },
    background: {
      default: '#FAFAFA', // --bg
      paper: '#FFFFFF', // --white
    },
    text: {
      primary: '#1F2937', // --ink
      secondary: '#6B7280', // --mid
    },
    grey: {
      50: '#F9FAFB',
      100: '#F3F4F6', // --line2
      200: '#E5E7EB', // --line
      300: '#D1D5DB',
      400: '#9CA3AF', // --soft
      500: '#6B7280', // --mid
      600: '#4B5563',
      700: '#374151', // --ink2
      800: '#1F2937', // --ink
      900: '#111827',
    },
  },
  typography: {
    fontFamily: '"Inter", system-ui, -apple-system, sans-serif',
    h1: {
      fontFamily: '"Playfair Display", Georgia, serif',
      fontWeight: 700,
      letterSpacing: '-0.5px',
    },
    h2: {
      fontFamily: '"Playfair Display", Georgia, serif',
      fontWeight: 700,
      letterSpacing: '-0.5px',
    },
    h3: {
      fontFamily: '"Playfair Display", Georgia, serif',
      fontWeight: 700,
      fontSize: '1.7rem',
      letterSpacing: '-0.5px',
    },
    h4: {
      fontFamily: '"Playfair Display", Georgia, serif',
      fontWeight: 700,
      fontSize: '1.5rem',
      letterSpacing: '-0.3px',
    },
    h5: {
      fontFamily: '"Playfair Display", Georgia, serif',
      fontWeight: 700,
      fontSize: '1.3rem',
      letterSpacing: '-0.3px',
    },
    h6: {
      fontWeight: 700,
      fontSize: '1rem',
      letterSpacing: '0.2px',
    },
    subtitle1: {
      fontSize: '0.95rem',
      fontWeight: 600,
    },
    subtitle2: {
      fontSize: '0.85rem',
      fontWeight: 600,
    },
    body1: {
      fontSize: '0.875rem',
      lineHeight: 1.5,
    },
    body2: {
      fontSize: '0.8125rem',
      lineHeight: 1.5,
    },
    caption: {
      fontSize: '0.75rem',
      lineHeight: 1.4,
    },
    button: {
      textTransform: 'none',
      fontWeight: 600,
    },
  },
  shape: {
    borderRadius: 6,
  },
  shadows: [
    'none',
    '0 1px 3px rgba(0,0,0,0.06)',
    '0 2px 6px rgba(0,0,0,0.08)',
    '0 4px 12px rgba(0,0,0,0.1)',
    '0 8px 24px rgba(0,0,0,0.12)',
    ...Array(20).fill('0 8px 24px rgba(0,0,0,0.12)'),
  ],
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          borderRadius: 6,
          fontWeight: 600,
          padding: '8px 20px',
          fontSize: '0.9rem',
        },
        contained: {
          boxShadow: 'none',
          '&:hover': {
            boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
          },
        },
        outlined: {
          borderWidth: 2,
          '&:hover': {
            borderWidth: 2,
          },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
          borderRadius: 8,
          border: '1px solid #E0E0E0',
          transition: 'all 0.3s ease',
          '&:hover': {
            boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          fontWeight: 600,
          fontSize: '0.8rem',
          height: 28,
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
        },
        elevation1: {
          boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
        },
      },
    },
    MuiTableHead: {
      styleOverrides: {
        root: {
          backgroundColor: '#F5F7FA',
          '& .MuiTableCell-root': {
            fontWeight: 600,
            fontSize: '0.85rem',
            color: '#2C3E50',
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
          },
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: {
          borderBottom: '1px solid #E8EAED',
          padding: '12px 16px',
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          fontWeight: 500,
        },
        standardSuccess: {
          backgroundColor: '#D5F5E3',
          color: '#27AE60',
        },
        standardError: {
          backgroundColor: '#FADBD8',
          color: '#E74C3C',
        },
        standardWarning: {
          backgroundColor: '#FCF3CF',
          color: '#F39C12',
        },
        standardInfo: {
          backgroundColor: '#D6EAF8',
          color: '#3498DB',
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          borderRadius: 4,
          height: 6,
        },
      },
    },
  },
})

export default theme
