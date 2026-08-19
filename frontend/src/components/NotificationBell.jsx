import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Button } from './ui/button';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';
import { Bell, CheckCheck, Package, AlertTriangle, Ban, Clock, Truck } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const TYPE_ICON = {
  job_offer: Package,
  driver_assigned: Truck,
  picked_up: Truck,
  delivered: CheckCheck,
  recipient_confirmed: CheckCheck,
  job_cancelled: Ban,
  driver_cancelled: Ban,
  job_returned: AlertTriangle,
  job_exception: AlertTriangle,
  stale_job: Clock,
};

const timeAgo = (iso) => {
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return 'now';
  if (mins < 60) return `${mins}m`;
  if (mins < 1440) return `${Math.floor(mins / 60)}h`;
  return `${Math.floor(mins / 1440)}d`;
};

export const NotificationBell = ({ dark = false }) => {
  const { token } = useAuth();
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const seenIds = useRef(null);

  const poll = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/notifications`, { headers: { Authorization: `Bearer ${token}` } });
      const notifs = r.data.notifications;
      if (seenIds.current !== null) {
        const fresh = notifs.filter((n) => !seenIds.current.has(n.id) && !n.read);
        fresh.slice(0, 3).forEach((n) => {
          toast(n.title, { description: n.body });
          if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
            try { new Notification(n.title, { body: n.body }); } catch { /* noop */ }
          }
        });
      }
      seenIds.current = new Set(notifs.map((n) => n.id));
      setItems(notifs);
      setUnread(r.data.unread);
    } catch { /* silent */ }
  }, [token]);

  useEffect(() => {
    poll();
    const id = setInterval(poll, 15000);
    return () => clearInterval(id);
  }, [poll]);

  const markAllRead = async () => {
    try {
      await axios.post(`${API}/notifications/read`, { all: true }, { headers: { Authorization: `Bearer ${token}` } });
      setUnread(0);
      setItems((prev) => prev.map((n) => ({ ...n, read: true })));
    } catch { /* noop */ }
  };

  const onOpen = (open) => {
    if (open && typeof Notification !== 'undefined' && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  };

  return (
    <Popover onOpenChange={onOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className={`relative px-2 ${dark ? 'text-white hover:bg-white/10' : ''}`} data-testid="notification-bell">
          <Bell className="w-5 h-5" />
          {unread > 0 && (
            <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center" data-testid="notification-badge">
              {unread > 99 ? '99+' : unread}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 p-0" data-testid="notification-panel">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-100">
          <p className="text-sm font-bold text-slate-900">Notifications</p>
          {unread > 0 && (
            <Button variant="ghost" size="sm" className="h-7 text-xs text-blue-600" onClick={markAllRead} data-testid="mark-all-read-btn">
              <CheckCheck className="w-3.5 h-3.5 mr-1" /> Mark all read
            </Button>
          )}
        </div>
        <div className="max-h-96 overflow-y-auto">
          {items.length === 0 && <p className="text-center text-sm text-slate-400 py-8">No notifications yet.</p>}
          {items.map((n) => {
            const Icon = TYPE_ICON[n.type] || Bell;
            return (
              <div key={n.id} className={`flex gap-3 px-4 py-3 border-b border-slate-50 ${n.read ? 'opacity-60' : 'bg-blue-50/40'}`} data-testid={`notification-item-${n.id}`}>
                <Icon className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-slate-900">{n.title || (n.type || '').replace(/_/g, ' ')}</p>
                  <p className="text-xs text-slate-500">{n.body || n.message}</p>
                  <p className="text-[10px] text-slate-400 mt-0.5">{timeAgo(n.created_at)} ago</p>
                </div>
              </div>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
};
