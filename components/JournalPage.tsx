import React, { useState, useEffect } from 'react';
import { 
  BookOpen, 
  Plus, 
  Search, 
  Edit3, 
  Trash2, 
  X,
  Save,
  Tag,
  Calendar,
  ChevronDown,
  ChevronUp,
  Briefcase
} from 'lucide-react';
import { Journal, StockGroup } from '../types';
import { Button } from './Button';

const API_BASE_URL = 'http://localhost:5000/api';

const CATEGORIES = ['분석', '복기', '전략', '메모', '뉴스'];

// 종목명 조회용 캐시
interface StockInfo {
  symbol: string;
  name: string;
}

export const JournalPage: React.FC = () => {
  const [journals, setJournals] = useState<Journal[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editingJournal, setEditingJournal] = useState<Journal | null>(null);
  const [expandedJournalId, setExpandedJournalId] = useState<string | null>(null);

  // 모든 종목 목록 (그룹에서 로드)
  const [allStocks, setAllStocks] = useState<StockInfo[]>([]);

  // Form states
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [category, setCategory] = useState('분석');
  const [tagInput, setTagInput] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [selectedStocks, setSelectedStocks] = useState<string[]>([]);
  const [stockSearchTerm, setStockSearchTerm] = useState('');

  // 종목 목록 로드
  const loadStocks = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/groups`);
      if (response.ok) {
        const groups: StockGroup[] = await response.json();
        const stocks: StockInfo[] = [];
        groups.forEach(g => {
          g.stocks.forEach(s => {
            if (!stocks.find(st => st.symbol === s.symbol)) {
              stocks.push({ symbol: s.symbol, name: s.name });
            }
          });
        });
        setAllStocks(stocks);
      }
    } catch (error) {
      console.error('종목 로딩 실패:', error);
    }
  };

  const loadJournals = async () => {
    setIsLoading(true);
    try {
      let url = `${API_BASE_URL}/journals`;
      if (selectedCategory) {
        url += `?category=${encodeURIComponent(selectedCategory)}`;
      }
      const response = await fetch(url);
      if (response.ok) {
        const data = await response.json();
        setJournals(data);
      }
    } catch (error) {
      console.error('일지 로딩 실패:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadJournals();
    loadStocks();
  }, [selectedCategory]);

  const resetForm = () => {
    setTitle('');
    setContent('');
    setCategory('분석');
    setTags([]);
    setTagInput('');
    setSelectedStocks([]);
    setStockSearchTerm('');
    setEditingJournal(null);
  };

  const openEditor = (journal?: Journal) => {
    if (journal) {
      setEditingJournal(journal);
      setTitle(journal.title);
      setContent(journal.content);
      setCategory(journal.category);
      setTags(journal.tags);
      setSelectedStocks(journal.stockSymbols || []);
    } else {
      resetForm();
    }
    setIsEditorOpen(true);
  };

  const closeEditor = () => {
    setIsEditorOpen(false);
    resetForm();
  };

  const handleAddTag = () => {
    const trimmed = tagInput.trim();
    if (trimmed && !tags.includes(trimmed)) {
      setTags([...tags, trimmed]);
      setTagInput('');
    }
  };

  const handleRemoveTag = (tag: string) => {
    setTags(tags.filter(t => t !== tag));
  };

  const handleSave = async () => {
    if (!title.trim()) {
      alert('제목을 입력해주세요.');
      return;
    }

    try {
      const body = { title, content, category, tags, stockSymbols: selectedStocks };
      
      if (editingJournal) {
        const response = await fetch(`${API_BASE_URL}/journals/${editingJournal.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        if (response.ok) {
          await loadJournals();
          closeEditor();
        }
      } else {
        const response = await fetch(`${API_BASE_URL}/journals`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        if (response.ok) {
          await loadJournals();
          closeEditor();
        }
      }
    } catch (error) {
      console.error('저장 실패:', error);
      alert('저장에 실패했습니다.');
    }
  };

  const toggleStock = (symbol: string) => {
    if (selectedStocks.includes(symbol)) {
      setSelectedStocks(selectedStocks.filter(s => s !== symbol));
    } else {
      setSelectedStocks([...selectedStocks, symbol]);
    }
  };

  const getStockName = (symbol: string) => {
    const stock = allStocks.find(s => s.symbol === symbol);
    return stock?.name || symbol;
  };

  const filteredStocksForSelection = allStocks.filter(s => 
    s.name.toLowerCase().includes(stockSearchTerm.toLowerCase()) ||
    s.symbol.includes(stockSearchTerm)
  );

  const handleDelete = async (journalId: string) => {
    if (!confirm('이 일지를 삭제하시겠습니까?')) return;

    try {
      const response = await fetch(`${API_BASE_URL}/journals/${journalId}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        await loadJournals();
      }
    } catch (error) {
      console.error('삭제 실패:', error);
    }
  };

  const filteredJournals = journals.filter(j => 
    j.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    j.content.toLowerCase().includes(searchTerm.toLowerCase()) ||
    j.tags.some(t => t.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('ko-KR', { 
      year: 'numeric', 
      month: 'short', 
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-black text-white tracking-tight">투자 일지</h1>
          <p className="text-slate-500 font-bold mt-1">분석 기록과 투자 복기를 관리하세요</p>
        </div>
        <Button onClick={() => openEditor()} variant="primary" size="md" className="px-6">
          <Plus className="w-5 h-5 mr-2" /> 새 일지 작성
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-4">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600" />
          <input 
            type="text" 
            placeholder="일지 검색..."
            className="w-full pl-12 pr-6 py-2.5 bg-[#1a1f2e] border border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-point-cyan focus:border-transparent transition-all placeholder-slate-600"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setSelectedCategory(null)}
            className={`px-4 py-2 rounded-xl text-sm font-bold transition-all ${
              selectedCategory === null 
                ? 'bg-point-cyan text-white' 
                : 'bg-[#1a1f2e] border border-slate-700 text-slate-400 hover:text-white'
            }`}
          >
            전체
          </button>
          {CATEGORIES.map(cat => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-4 py-2 rounded-xl text-sm font-bold transition-all ${
                selectedCategory === cat 
                  ? 'bg-point-cyan text-white' 
                  : 'bg-[#1a1f2e] border border-slate-700 text-slate-400 hover:text-white'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Journal List */}
      {isLoading ? (
        <div className="text-center py-12 text-slate-500">로딩 중...</div>
      ) : filteredJournals.length === 0 ? (
        <div className="bg-[#1a1f2e] border border-dashed border-slate-700 rounded-2xl py-16 text-center">
          <BookOpen className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <p className="text-slate-500 font-bold">작성된 일지가 없습니다.</p>
          <Button onClick={() => openEditor()} variant="ghost" size="sm" className="mt-4">
            첫 번째 일지 작성하기
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredJournals.map(journal => (
            <div 
              key={journal.id}
              className="bg-[#1a1f2e] border border-slate-800 rounded-2xl overflow-hidden hover:border-slate-700 transition-all"
            >
              <div 
                className="p-5 cursor-pointer"
                onClick={() => setExpandedJournalId(expandedJournalId === journal.id ? null : journal.id)}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-lg bg-point-cyan/10 text-point-cyan">
                        {journal.category}
                      </span>
                      <span className="text-[10px] text-slate-500 flex items-center gap-1">
                        <Calendar className="w-3 h-3" />
                        {formatDate(journal.createdAt)}
                      </span>
                    </div>
                    <h3 className="text-lg font-bold text-white">{journal.title}</h3>
                    {expandedJournalId !== journal.id && (
                      <p className="text-sm text-slate-500 mt-2 line-clamp-2">{journal.content}</p>
                    )}
                    {journal.tags.length > 0 && (
                      <div className="flex flex-wrap gap-2 mt-3">
                        {journal.tags.map(tag => (
                          <span key={tag} className="text-[10px] px-2 py-1 rounded-lg bg-slate-800 text-slate-400">
                            #{tag}
                          </span>
                        ))}
                      </div>
                    )}
                    {journal.stockSymbols && journal.stockSymbols.length > 0 && (
                      <div className="flex flex-wrap gap-2 mt-2">
                        {journal.stockSymbols.map(symbol => (
                          <span key={symbol} className="text-[10px] px-2 py-1 rounded-lg bg-violet-500/10 text-violet-400 flex items-center gap-1">
                            <Briefcase className="w-3 h-3" />
                            {getStockName(symbol)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={(e) => { e.stopPropagation(); openEditor(journal); }}
                      className="p-2 text-slate-500 hover:text-point-cyan transition-colors"
                    >
                      <Edit3 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDelete(journal.id); }}
                      className="p-2 text-slate-500 hover:text-rose-400 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                    {expandedJournalId === journal.id ? (
                      <ChevronUp className="w-5 h-5 text-slate-500" />
                    ) : (
                      <ChevronDown className="w-5 h-5 text-slate-500" />
                    )}
                  </div>
                </div>
              </div>
              
              {expandedJournalId === journal.id && (
                <div className="px-5 pb-5 pt-0 border-t border-slate-800">
                  <div className="prose prose-invert prose-sm max-w-none pt-4">
                    <pre className="whitespace-pre-wrap font-sans text-slate-300 text-sm leading-relaxed">
                      {journal.content}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Editor Modal */}
      {isEditorOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#1a1f2e] border border-slate-700 rounded-2xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between p-5 border-b border-slate-800">
              <h2 className="text-xl font-bold text-white">
                {editingJournal ? '일지 수정' : '새 일지 작성'}
              </h2>
              <button onClick={closeEditor} className="text-slate-500 hover:text-white transition-colors">
                <X className="w-6 h-6" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              {/* Title */}
              <div>
                <label className="block text-sm font-bold text-slate-400 mb-2">제목</label>
                <input 
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="일지 제목을 입력하세요"
                  className="w-full px-4 py-3 bg-[#0f121d] border border-slate-700 rounded-xl text-white font-bold focus:ring-2 focus:ring-point-cyan focus:border-transparent transition-all"
                />
              </div>

              {/* Category */}
              <div>
                <label className="block text-sm font-bold text-slate-400 mb-2">카테고리</label>
                <div className="flex flex-wrap gap-2">
                  {CATEGORIES.map(cat => (
                    <button
                      key={cat}
                      onClick={() => setCategory(cat)}
                      className={`px-4 py-2 rounded-xl text-sm font-bold transition-all ${
                        category === cat 
                          ? 'bg-point-cyan text-white' 
                          : 'bg-[#0f121d] border border-slate-700 text-slate-400 hover:text-white'
                      }`}
                    >
                      {cat}
                    </button>
                  ))}
                </div>
              </div>

              {/* Content */}
              <div>
                <label className="block text-sm font-bold text-slate-400 mb-2">내용</label>
                <textarea 
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder="분석 내용, 투자 복기, 전략 등을 기록하세요..."
                  rows={12}
                  className="w-full px-4 py-3 bg-[#0f121d] border border-slate-700 rounded-xl text-white focus:ring-2 focus:ring-point-cyan focus:border-transparent transition-all resize-none"
                />
              </div>

              {/* Tags */}
              <div>
                <label className="block text-sm font-bold text-slate-400 mb-2">태그</label>
                <div className="flex gap-2 mb-3">
                  <input 
                    type="text"
                    value={tagInput}
                    onChange={(e) => setTagInput(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && handleAddTag()}
                    placeholder="태그 입력 후 Enter"
                    className="flex-1 px-4 py-2 bg-[#0f121d] border border-slate-700 rounded-xl text-white text-sm focus:ring-2 focus:ring-point-cyan focus:border-transparent transition-all"
                  />
                  <button 
                    onClick={handleAddTag}
                    className="px-4 py-2 bg-slate-800 text-slate-400 hover:text-white rounded-xl text-sm font-bold transition-colors"
                  >
                    <Tag className="w-4 h-4" />
                  </button>
                </div>
                {tags.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {tags.map(tag => (
                      <span 
                        key={tag} 
                        className="flex items-center gap-1 text-sm px-3 py-1 rounded-lg bg-point-cyan/10 text-point-cyan"
                      >
                        #{tag}
                        <button onClick={() => handleRemoveTag(tag)} className="hover:text-white">
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Stock Selection */}
              <div>
                <label className="block text-sm font-bold text-slate-400 mb-2">
                  관련 종목 <span className="text-slate-600">(복수 선택 가능)</span>
                </label>
                <div className="flex gap-2 mb-3">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600" />
                    <input 
                      type="text"
                      value={stockSearchTerm}
                      onChange={(e) => setStockSearchTerm(e.target.value)}
                      placeholder="종목 검색..."
                      className="w-full pl-10 pr-4 py-2 bg-[#0f121d] border border-slate-700 rounded-xl text-white text-sm focus:ring-2 focus:ring-point-cyan focus:border-transparent transition-all"
                    />
                  </div>
                </div>
                {selectedStocks.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-3">
                    {selectedStocks.map(symbol => (
                      <span 
                        key={symbol} 
                        className="flex items-center gap-1 text-sm px-3 py-1 rounded-lg bg-violet-500/10 text-violet-400"
                      >
                        <Briefcase className="w-3 h-3" />
                        {getStockName(symbol)}
                        <button onClick={() => toggleStock(symbol)} className="hover:text-white ml-1">
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}
                {stockSearchTerm && filteredStocksForSelection.length > 0 && (
                  <div className="bg-[#0f121d] border border-slate-700 rounded-xl max-h-40 overflow-y-auto">
                    {filteredStocksForSelection.slice(0, 10).map(stock => (
                      <button
                        key={stock.symbol}
                        onClick={() => {
                          toggleStock(stock.symbol);
                          setStockSearchTerm('');
                        }}
                        className={`w-full text-left px-4 py-2 hover:bg-slate-800 transition-colors flex items-center justify-between ${
                          selectedStocks.includes(stock.symbol) ? 'bg-violet-500/10' : ''
                        }`}
                      >
                        <span className="text-sm text-white">{stock.name}</span>
                        <span className="text-xs text-slate-500">{stock.symbol}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Footer */}
            <div className="flex justify-end gap-3 p-5 border-t border-slate-800">
              <Button onClick={closeEditor} variant="ghost" size="md">
                취소
              </Button>
              <Button onClick={handleSave} variant="primary" size="md" className="px-8">
                <Save className="w-4 h-4 mr-2" /> 저장
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
