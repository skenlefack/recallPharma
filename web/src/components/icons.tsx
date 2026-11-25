/** Icônes en ligne (traits 1,75 px, couleur du texte) : aucune ressource externe. */
type Props = { size?: number; className?: string };

function Svg({ size = 18, className, children }: Props & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={className}
    >
      {children}
    </svg>
  );
}

export const SearchIcon = (p: Props) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.5-3.5" />
  </Svg>
);

export const BellIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
    <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
  </Svg>
);

export const ChatIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    <path d="M8 9h8M8 13h5" />
  </Svg>
);

export const CheckShieldIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
    <path d="m9 12 2 2 4-4" />
  </Svg>
);

export const DocumentIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6M8 13h8M8 17h6" />
  </Svg>
);

export const ArrowRightIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </Svg>
);

export const LogoutIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
  </Svg>
);

export const ClockIcon = (p: Props) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </Svg>
);

export const GlobeIcon = (p: Props) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" />
  </Svg>
);

export const LayersIcon = (p: Props) => (
  <Svg {...p}>
    <path d="m12 3 9 5-9 5-9-5z" />
    <path d="m3 13 9 5 9-5" />
  </Svg>
);

export const UsersIcon = (p: Props) => (
  <Svg {...p}>
    <circle cx="9" cy="8" r="3.5" />
    <path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6" />
  </Svg>
);

export const AlertTriangleIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0" />
    <path d="M12 9v4M12 17h.01" />
  </Svg>
);

export const PackageIcon = (p: Props) => (
  <Svg {...p}>
    <path d="m21 8-9-5-9 5v8l9 5 9-5z" />
    <path d="m3 8 9 5 9-5M12 13v8M7.5 5.5l9 5" />
  </Svg>
);

export const BanIcon = (p: Props) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="m5.7 5.7 12.6 12.6" />
  </Svg>
);

export const PauseIcon = (p: Props) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M10 9v6M14 9v6" />
  </Svg>
);

export const InfoIcon = (p: Props) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 16v-5M12 8h.01" />
  </Svg>
);

export const MapPinIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21" />
    <circle cx="12" cy="9.5" r="2.5" />
  </Svg>
);

export const SendIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M22 2 11 13M22 2l-7 20-4-9-9-4z" />
  </Svg>
);

export const SparkIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6" />
  </Svg>
);

export const LockIcon = (p: Props) => (
  <Svg {...p}>
    <rect x="4" y="11" width="16" height="10" rx="2" />
    <path d="M8 11V7a4 4 0 0 1 8 0v4" />
  </Svg>
);

export const TrashIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
  </Svg>
);

export const ThumbUpIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M7 10v11H3V10zM7 10l4-8a3 3 0 0 1 3 3v4h5.5a2 2 0 0 1 2 2.3l-1.4 8A2 2 0 0 1 18.1 21H7" />
  </Svg>
);

export const FlagIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M4 22V4M4 4h13l-2 4 2 4H4" />
  </Svg>
);

export const PillIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M10.5 20.5a5 5 0 0 1-7-7l10-10a5 5 0 0 1 7 7z" />
    <path d="m8.5 8.5 7 7" />
  </Svg>
);

export const WormIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M4 18c2.5 0 2.5-4 5-4s2.5 4 5 4 2.5-4 5-4" />
    <path d="M4 10c2.5 0 2.5-4 5-4s2.5 4 5 4 2.5-4 5-4" />
  </Svg>
);

export const BugIcon = (p: Props) => (
  <Svg {...p}>
    <rect x="8" y="7" width="8" height="13" rx="4" />
    <path d="M12 7V4M9 4l1.5 2M15 4l-1.5 2M3 13h5M16 13h5M4 8l4 2M20 8l-4 2M4 19l4-2M20 19l-4-2" />
  </Svg>
);

export const MicroscopeIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M6 21h12M9 17h6M12 17v4M10 3l4 2-4 8-4-2z" />
    <path d="M13.5 9.5A5 5 0 0 1 17 17" />
  </Svg>
);

export const ThermometerIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M14 14.8V4a2 2 0 0 0-4 0v10.8a4 4 0 1 0 4 0" />
    <path d="M12 10v7" />
  </Svg>
);

export const CalendarIcon = (p: Props) => (
  <Svg {...p}>
    <rect x="3" y="5" width="18" height="16" rx="2" />
    <path d="M3 10h18M8 3v4M16 3v4" />
  </Svg>
);

export const CloseIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Svg>
);

export const MailIcon = (p: Props) => (
  <Svg {...p}>
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <path d="m3 7 9 6 9-6" />
  </Svg>
);

export const EyeIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12" />
    <circle cx="12" cy="12" r="3" />
  </Svg>
);

export const EyeOffIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-2.2 3.1M6.6 6.6A17 17 0 0 0 2 12s3.5 7 10 7a9.7 9.7 0 0 0 5.4-1.6" />
    <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2M3 3l18 18" />
  </Svg>
);
