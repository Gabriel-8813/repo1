import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const POLL_INTERVAL_MS = 15000;

// Polls /api/jobs/available every 15s and toasts on newly appearing urgent/emergency jobs.
// Returns { urgentCount, newlyArrived } so pages can render a banner if desired.
export function useUrgentJobAlerts(token, enabled = true) {
  const [urgentCount, setUrgentCount] = useState(0);
  const [newlyArrived, setNewlyArrived] = useState([]);
  const seenIds = useRef(new Set());
  const firstRun = useRef(true);

  useEffect(() => {
    if (!token || !enabled) return;

    let cancelled = false;

    const poll = async () => {
      try {
        const r = await axios.get(`${API}/jobs/available`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (cancelled) return;
        const jobs = r.data.jobs || [];
        const urgentJobs = jobs.filter(j => j.urgency === 'urgent' || j.urgency === 'emergency');
        setUrgentCount(urgentJobs.length);

        if (firstRun.current) {
          // First poll: seed the seen set, don't toast existing jobs
          urgentJobs.forEach(j => seenIds.current.add(j.id));
          firstRun.current = false;
          return;
        }

        const newOnes = urgentJobs.filter(j => !seenIds.current.has(j.id));
        if (newOnes.length > 0) {
          newOnes.forEach(j => {
            seenIds.current.add(j.id);
            const isEmergency = j.urgency === 'emergency';
            toast[isEmergency ? 'error' : 'warning'](
              `${isEmergency ? '🚨 EMERGENCY' : '⚡ URGENT'}: ${j.title}`,
              {
                description: `${j.pickup_city} → ${j.delivery_city} · $${j.offered_price.toFixed(2)}`,
                duration: 8000,
              }
            );
          });
          setNewlyArrived(prev => [...newOnes, ...prev].slice(0, 10));
        }
      } catch (err) {
        // silent fail; will retry on next tick
      }
    };

    poll();
    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [token, enabled]);

  const clearNewlyArrived = () => setNewlyArrived([]);

  return { urgentCount, newlyArrived, clearNewlyArrived };
}
