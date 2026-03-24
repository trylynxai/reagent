import { useState, useEffect, useCallback, useRef } from 'react';
import { useLocation } from 'react-router-dom';

const DETAIL_ROUTES = ['/trace/', '/replay/'];

export const AUTO_REFRESH_INTERVAL = 10000;

export function useAutoRefresh(fetchFn, interval = AUTO_REFRESH_INTERVAL) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const location = useLocation();
  const previousDataRef = useRef(null);

  const isDetailPage = DETAIL_ROUTES.some(route => 
    location.pathname.startsWith(route)
  );

  const fetchData = useCallback(async () => {
    if (isDetailPage) return;

    try {
      const result = await fetchFn();
      
      if (result && typeof result === 'object') {
        const resultStr = JSON.stringify(result);
        
        if (previousDataRef.current !== resultStr) {
          previousDataRef.current = resultStr;
          setData(result);
        }
      } else {
        setData(result);
      }
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [fetchFn, isDetailPage]);

  useEffect(() => {
    if (isDetailPage) {
      setData(null);
      previousDataRef.current = null;
      return;
    }

    fetchData();

    const timer = setInterval(fetchData, interval);

    return () => clearInterval(timer);
  }, [fetchData, interval, isDetailPage, location.pathname]);

  return { data, loading, error, refetch: fetchData };
}

export default useAutoRefresh;
