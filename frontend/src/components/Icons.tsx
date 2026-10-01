// Small stroke icons used across the app. They take the text colour (currentColor).
import type { ReactNode } from 'react'

function Icon({ size = 18, children }: { size?: number; children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  )
}

type IconProps = { size?: number }

export const IconUpload = ({ size }: IconProps) => (
  <Icon size={size}>
    <path d="M12 16V4M7 9l5-5 5 5" />
    <path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
  </Icon>
)

export const IconSearch = ({ size }: IconProps) => (
  <Icon size={size}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.5-3.5" />
  </Icon>
)

export const IconOpen = ({ size }: IconProps) => (
  <Icon size={size}>
    <path d="M14 4h6v6M20 4l-9 9" />
    <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
  </Icon>
)

export const IconMore = ({ size = 18 }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <circle cx="5" cy="12" r="1.8" />
    <circle cx="12" cy="12" r="1.8" />
    <circle cx="19" cy="12" r="1.8" />
  </svg>
)

export const IconSparkle = ({ size }: IconProps) => (
  <Icon size={size}>
    <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />
    <path d="M19 17l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z" />
  </Icon>
)

export const IconSend = ({ size }: IconProps) => (
  <Icon size={size}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </Icon>
)

export const IconClose = ({ size }: IconProps) => (
  <Icon size={size}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Icon>
)

export const IconCheck = ({ size }: IconProps) => (
  <Icon size={size}>
    <path d="M5 12l5 5L20 7" />
  </Icon>
)

export const IconText = ({ size }: IconProps) => (
  <Icon size={size}>
    <path d="M4 6h16M4 12h16M4 18h10" />
  </Icon>
)

export const IconRefresh = ({ size }: IconProps) => (
  <Icon size={size}>
    <path d="M3 12a9 9 0 0 1 15.5-6.2L21 8M21 3v5h-5" />
    <path d="M21 12a9 9 0 0 1-15.5 6.2L3 16M3 21v-5h5" />
  </Icon>
)

export const IconTrash = ({ size }: IconProps) => (
  <Icon size={size}>
    <path d="M4 7h16M10 11v6M14 11v6" />
    <path d="M6 7l1 13h10l1-13M9 7V4h6v3" />
  </Icon>
)

export const IconAlert = ({ size }: IconProps) => (
  <Icon size={size}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 8v4M12 16h.01" />
  </Icon>
)

export const IconGrid = ({ size }: IconProps) => (
  <Icon size={size}>
    <rect x="3" y="3" width="7" height="7" rx="1.5" />
    <rect x="14" y="3" width="7" height="7" rx="1.5" />
    <rect x="3" y="14" width="7" height="7" rx="1.5" />
    <rect x="14" y="14" width="7" height="7" rx="1.5" />
  </Icon>
)

export const IconChevron = ({ size, left = false }: IconProps & { left?: boolean }) => (
  <Icon size={size}>{left ? <path d="M15 6l-6 6 6 6" /> : <path d="M9 6l6 6-6 6" />}</Icon>
)

export const IconLogout = ({ size }: IconProps) => (
  <Icon size={size}>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <path d="M16 17l5-5-5-5M21 12H9" />
  </Icon>
)
