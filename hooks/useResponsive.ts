import { useState, useEffect } from 'react';

// iPhone 17 예상 사이즈 및 일반 모바일 브레이크포인트
const MOBILE_BREAKPOINT = 768;
const TABLET_BREAKPOINT = 1024;

export interface DeviceInfo {
  isMobile: boolean;
  isTablet: boolean;
  isDesktop: boolean;
  width: number;
  height: number;
  isLandscape: boolean;
  isTouchDevice: boolean;
}

export const useResponsive = (): DeviceInfo => {
  const [deviceInfo, setDeviceInfo] = useState<DeviceInfo>(() => ({
    isMobile: typeof window !== 'undefined' ? window.innerWidth < MOBILE_BREAKPOINT : false,
    isTablet: typeof window !== 'undefined' ? window.innerWidth >= MOBILE_BREAKPOINT && window.innerWidth < TABLET_BREAKPOINT : false,
    isDesktop: typeof window !== 'undefined' ? window.innerWidth >= TABLET_BREAKPOINT : true,
    width: typeof window !== 'undefined' ? window.innerWidth : 1920,
    height: typeof window !== 'undefined' ? window.innerHeight : 1080,
    isLandscape: typeof window !== 'undefined' ? window.innerWidth > window.innerHeight : true,
    isTouchDevice: typeof window !== 'undefined' ? ('ontouchstart' in window || navigator.maxTouchPoints > 0) : false,
  }));

  useEffect(() => {
    const handleResize = () => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      
      setDeviceInfo({
        isMobile: width < MOBILE_BREAKPOINT,
        isTablet: width >= MOBILE_BREAKPOINT && width < TABLET_BREAKPOINT,
        isDesktop: width >= TABLET_BREAKPOINT,
        width,
        height,
        isLandscape: width > height,
        isTouchDevice: 'ontouchstart' in window || navigator.maxTouchPoints > 0,
      });
    };

    // 초기 설정
    handleResize();

    // 리사이즈 이벤트 리스너
    window.addEventListener('resize', handleResize);
    window.addEventListener('orientationchange', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('orientationchange', handleResize);
    };
  }, []);

  return deviceInfo;
};

// 모바일 감지 유틸리티 함수
export const isMobileDevice = (): boolean => {
  if (typeof window === 'undefined') return false;
  
  // User agent 체크
  const userAgent = navigator.userAgent.toLowerCase();
  const mobileKeywords = ['iphone', 'ipad', 'android', 'mobile', 'webos', 'blackberry', 'opera mini', 'iemobile'];
  const isMobileUA = mobileKeywords.some(keyword => userAgent.includes(keyword));
  
  // 화면 크기 체크
  const isSmallScreen = window.innerWidth < MOBILE_BREAKPOINT;
  
  // 터치 지원 체크
  const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  
  return isMobileUA || (isSmallScreen && isTouchDevice);
};
