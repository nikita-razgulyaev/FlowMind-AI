/** Знак FlowMind AI: ветвление (один вход → три результата) с градиентом, как в документации. */
export default function LogoIcon({ className = "w-5 h-5" }: { className?: string }) {
    // Уникальный id градиента, чтобы несколько иконок на странице не конфликтовали
    const gid = "fm-logo-g";
    return (
        <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 64 64"
            className={className}
            aria-hidden
        >
            <defs>
                <linearGradient id={gid} x1="0" y1="0" x2="64" y2="64" gradientUnits="userSpaceOnUse">
                    <stop stopColor="#2563eb" />
                    <stop offset="1" stopColor="#06b6d4" />
                </linearGradient>
            </defs>
            <rect width="64" height="64" rx="16" fill={`url(#${gid})`} />
            <g
                stroke="#fff"
                strokeWidth="3.4"
                strokeLinecap="round"
                strokeLinejoin="round"
                fill="none"
            >
                <path d="M16 32 H28" />
                <path d="M28 32 C 36 32, 36 17, 46 17" />
                <path d="M28 32 H46" />
                <path d="M28 32 C 36 32, 36 47, 46 47" />
            </g>
            <g fill="#fff">
                <circle cx="16" cy="32" r="4.2" />
                <circle cx="47" cy="17" r="4.2" />
                <circle cx="47" cy="32" r="4.2" />
                <circle cx="47" cy="47" r="4.2" />
            </g>
        </svg>
    );
}
