import React, { useState, useEffect, useRef } from 'react';
import { 
  TrendingUp, 
  LayoutDashboard, 
  Briefcase, 
  BookOpen,
  Sparkles,
  Menu,
  X,
  Bot
} from 'lucide-react';
import { PageType } from '../types';

interface MobileNavProps {
  currentPage: PageType;
  onPageChange: (page: PageType) => void;
}

const menuItems: { id: PageType; label: string; icon: React.ReactNode; description: string }[] = [
  { 
    id: 'recommendations', 
    label: 'AI추천', 
    icon: <Sparkles className="w-5 h-5" />,
    description: 'Filter2 기반 예측'
  },
  { 
    id: 'autotrading', 
    label: '자동매매', 
    icon: <Bot className="w-5 h-5" />,
    description: '전략 기반 자동 거래'
  },
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
    id: 'journal', 
    label: '투자 일지', 
    icon: <BookOpen className="w-5 h-5" />,
    description: '분석 기록 및 복기'
  },
];

export const MobileNav: React.FC<MobileNavProps> = ({ currentPage, onPageChange }) => {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // 메뉴 외부 클릭 시 닫기
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // ESC 키로 메뉴 닫기
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsOpen(false);
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, []);

  const handlePageChange = (page: PageType) => {
    onPageChange(page);
    setIsOpen(false);
  };

  const currentMenuItem = menuItems.find(item => item.id === currentPage);

  return (
    <>
      {/* 고정 헤더 */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-[#0b0d14]/95 backdrop-blur-lg border-b border-slate-800 safe-area-top">
        <div className="flex items-center justify-between px-4 py-3">
          {/* 로고 */}
          <div className="flex items-center gap-2">
            <div className="bg-point-cyan p-1.5 rounded-lg shadow-lg shadow-point-cyan/20">
              <TrendingUp className="w-5 h-5 text-white" />
            </div>
            <div className="flex flex-col">
              <span className="text-base font-black tracking-tighter text-white leading-none">마이스탁</span>
              <span className="text-[7px] font-bold text-slate-500 tracking-[0.1em] uppercase">My Market</span>
            </div>
          </div>

          {/* 현재 페이지 표시 + 메뉴 버튼 */}
          <div className="flex items-center gap-3">
            <span className="text-xs font-bold text-point-cyan bg-point-cyan/10 px-2 py-1 rounded-lg border border-point-cyan/30">
              {currentMenuItem?.label}
            </span>
            <button
              onClick={() => setIsOpen(!isOpen)}
              className="p-2 rounded-xl bg-slate-800/50 hover:bg-slate-700 text-white transition-all active:scale-95"
              aria-label="메뉴 열기"
            >
              {isOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </header>

      {/* 오버레이 */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 animate-in fade-in duration-200"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* 슬라이드 메뉴 */}
      <div
        ref={menuRef}
        className={`fixed top-0 right-0 h-full w-72 bg-[#0b0d14] border-l border-slate-800 z-50 transform transition-transform duration-300 ease-out ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {/* 메뉴 헤더 */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between safe-area-top pt-4">
          <span className="text-sm font-bold text-white">메뉴</span>
          <button
            onClick={() => setIsOpen(false)}
            className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-all"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 메뉴 아이템 */}
        <nav className="p-3 space-y-2">
          {menuItems.map((item) => {
            const isActive = currentPage === item.id;
            return (
              <button
                key={item.id}
                onClick={() => handlePageChange(item.id)}
                className={`w-full flex items-center gap-3 p-4 rounded-xl transition-all active:scale-[0.98] ${
                  isActive 
                    ? 'bg-point-cyan/10 border border-point-cyan/30 text-point-cyan' 
                    : 'hover:bg-slate-800/50 text-slate-400 hover:text-white border border-transparent'
                }`}
              >
                <div className={`p-2 rounded-lg ${isActive ? 'bg-point-cyan/20 text-point-cyan' : 'bg-slate-800 text-slate-500'}`}>
                  {item.icon}
                </div>
                <div className="text-left">
                  <div className={`text-sm font-bold ${isActive ? 'text-white' : ''}`}>{item.label}</div>
                  <div className="text-[10px] text-slate-500">{item.description}</div>
                </div>
              </button>
            );
          })}
        </nav>

        {/* 메뉴 푸터 */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-slate-800 safe-area-bottom">
          <div className="text-[10px] text-slate-600 text-center font-bold uppercase tracking-widest">
            © {new Date().getFullYear()} MYSTOCK
          </div>
        </div>
      </div>
    </>
  );
};
