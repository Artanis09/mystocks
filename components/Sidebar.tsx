import React from 'react';
import { 
  TrendingUp, 
  LayoutDashboard, 
  Briefcase, 
  BookOpen,
  ChevronRight,
  Sparkles
} from 'lucide-react';
import { PageType } from '../types';

interface SidebarProps {
  currentPage: PageType;
  onPageChange: (page: PageType) => void;
}

const menuItems: { id: PageType; label: string; icon: React.ReactNode; description: string }[] = [
  { 
    id: 'dashboard', 
    label: '대시보드', 
    icon: <LayoutDashboard className="w-5 h-5" />,
    description: '시장 지수 및 동향'
  },
  { 
    id: 'portfolio', 
    label: '포트폴리오', 
    icon: <Briefcase className="w-5 h-5" />,
    description: '종목 분석 및 관리'
  },
  { 
    id: 'recommendations', 
    label: 'AI 투자', 
    icon: <Sparkles className="w-5 h-5" />,
    description: 'AI 선정 전략 종목'
  },
  { 
    id: 'journal', 
    label: '투자 일지', 
    icon: <BookOpen className="w-5 h-5" />,
    description: '분석 기록 및 복기'
  },
];

export const Sidebar: React.FC<SidebarProps> = ({ currentPage, onPageChange }) => {
  return (
    <aside className="w-64 bg-[#0b0d14] border-r border-slate-800 min-h-screen flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-slate-800">
        <div className="flex items-center space-x-3 cursor-pointer group">
          <div className="bg-point-cyan p-2 rounded-xl shadow-lg shadow-point-cyan/20 group-hover:scale-105 transition-all">
            <TrendingUp className="w-6 h-6 text-white" />
          </div>
          <div className="flex flex-col">
            <span className="text-xl font-black tracking-tighter text-white leading-none">마이스탁</span>
            <span className="text-[8px] font-bold text-slate-500 tracking-[0.15em] uppercase mt-1">My Market Insight</span>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-2">
        {menuItems.map((item) => {
          const isActive = currentPage === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onPageChange(item.id)}
              className={`w-full flex items-center justify-between p-3 rounded-xl transition-all group ${
                isActive 
                  ? 'bg-point-cyan/10 border border-point-cyan/30 text-point-cyan' 
                  : 'hover:bg-slate-800/50 text-slate-400 hover:text-white border border-transparent'
              }`}
            >
              <div className="flex items-center gap-3">
                <div className={`${isActive ? 'text-point-cyan' : 'text-slate-500 group-hover:text-white'}`}>
                  {item.icon}
                </div>
                <div className="text-left">
                  <div className={`text-sm font-bold ${isActive ? 'text-white' : ''}`}>{item.label}</div>
                  <div className="text-[10px] text-slate-500">{item.description}</div>
                </div>
              </div>
              {isActive && <ChevronRight className="w-4 h-4 text-point-cyan" />}
            </button>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-slate-800">
        <div className="text-[10px] text-slate-600 text-center font-bold uppercase tracking-widest">
          © {new Date().getFullYear()} MYSTOCK
        </div>
      </div>
    </aside>
  );
};
