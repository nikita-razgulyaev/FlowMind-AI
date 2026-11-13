/** Знак FlowMind AI: ветвление (один вход → три результата), вариант 1. */
export default function LogoIcon({ className = "w-5 h-5" }: { className?: string }) {
    return (
        <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 64 64"
            className={className}
            aria-hidden
        >
            <rect width="64" height="64" rx="16" fill="currentColor" />
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
