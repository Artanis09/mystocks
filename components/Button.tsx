
import React from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'success' | 'warning';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  isLoading = false,
  className = '',
  ...props
}) => {
  const baseStyles = 'inline-flex items-center justify-center font-bold transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-[#0f121d] disabled:opacity-50 disabled:cursor-not-allowed rounded-xl active:scale-95';
  
  const variants = {
    primary: 'bg-point-cyan text-white hover:bg-cyan-400 focus:ring-cyan-500',
    success: 'bg-point-green text-white hover:bg-green-400 focus:ring-green-500',
    warning: 'bg-point-orange text-white hover:bg-orange-400 focus:ring-orange-500',
    secondary: 'bg-slate-700 text-slate-200 border border-slate-600 hover:bg-slate-600 focus:ring-slate-500',
    danger: 'bg-rose-500 text-white hover:bg-rose-400 focus:ring-rose-500',
    ghost: 'bg-transparent text-slate-400 hover:bg-slate-800 hover:text-white',
    vivid: 'bg-point-cyan text-white hover:bg-cyan-400 focus:ring-cyan-500', // backward compatibility
  };

  const sizes = {
    sm: 'px-4 py-2 text-xs',
    md: 'px-5 py-2.5 text-sm',
    lg: 'px-8 py-3.5 text-base',
  };

  return (
    <button
      className={`${baseStyles} ${variants[variant === 'vivid' ? 'primary' : variant]} ${sizes[size]} ${className}`}
      disabled={isLoading || props.disabled}
      {...props}
    >
      {isLoading && (
        <svg className="animate-spin -ml-1 mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
      )}
      {children}
    </button>
  );
};
