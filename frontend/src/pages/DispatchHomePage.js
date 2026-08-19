import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { NotificationBell } from '../components/NotificationBell';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Truck, LogOut, Radio, Snowflake, Zap, Lock, PenLine, CreditCard, Package, Clock, UserPlus, XCircle } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const COLUMNS = [
  ['Open Pool', ['created', 'open']], ['Offered', ['offered']], ['Accepted', ['accepted', 'in_progress']],
  ['Picked Up', ['picked_up']], ['In Transit', ['in_transit']], ['Delivered', ['delivered', 'completed']],
  ['Exceptions', ['returned', 'cancelled']]
];
const STALE_MIN = { created: 30, open: 30, offered: 30, accepted: 20, in_progress: 20, picked_up: 60, in_transit: 60 };
const FLAG_ICONS = { cold_chain: Snowflake, urgent: Zap, controlled_substance: Lock, signature_required: PenLine, id_required: CreditCard, fragile: Package };
const EVENT_LABELS = { pickup_confirmed: 'Pickup confirmed', in_transit_ping: 'Transit ping', delivery_attempted: 'Delivery attempted', delivered: 'Delivered', returned: 'Returned', exception: 'Exception' };

const minsIn = (iso) => iso ? Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000)) : 0;
const fmtMins = (m) => m < 60 ? `${m}m` : `${Math.floor(m / 60)}h ${m % 60}m`;

export default function DispatchHomePage() {
  const { user, token, logout } = useAuth();
  const navigate = useNavigate();
  const headers = { Authorization: `Bearer ${token}` };
  const [jobs, setJobs] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [selected, setSelected] = useState(null);
  const [events, setEvents] = useState(null);
  const [assignTo, setAssignTo] = useState('');
  const [confirmCancel, setConfirmCancel] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/dispatch/board`, { headers });
      setJobs(r.data.jobs);
      setDrivers(r.data.approved_drivers);
      setSelected((prev) => prev ? (r.data.jobs.find((j) => j.id === prev.id) || prev) : prev);
    } catch { toast.error('Failed to load board'); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { load(); const iv = setInterval(load, 10000); return () => clearInterval(iv); }, [load]);

  const openJob = async (job) => {
    setSelected(job); setEvents(null); setAssignTo(job.assigned_driver_id || ''); setConfirmCancel(false);
    try {
      const r = await axios.get(`${API}/jobs/${job.id}/custody-events`, { headers });
      setEvents(r.data.custody_events);
    } catch { setEvents([]); }
  };

  const assign = async () => {
    if (!assignTo) return toast.error('Pick a driver');
    try {
      await axios.put(`${API}/jobs/${selected.id}`, { assigned_driver_id: assignTo, status: 'offered' }, { headers });
      toast.success('Job offered to driver');
      setSelected(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Assign failed'); }
  };

  const cancelJob = async () => {
    try {
      await axios.put(`${API}/jobs/${selected.id}`, { status: 'cancelled' }, { headers });
      toast.success('Job cancelled');
      setSelected(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Cancel failed'); }
  };

  const alertLevel = (j) => {
    if ((j.handling_flags || []).includes('urgent') || j.urgency === 'urgent' || j.urgency === 'emergency') return 'red';
    if (['returned', 'cancelled'].includes(j.status)) return 'red';
    const lim = STALE_MIN[j.status];
    if (lim && minsIn(j.status_since) > lim) return 'amber';
    return null;
  };

  return (
    <div className="min-h-screen bg-slate-100" data-testid="dispatch-home">
      <header className="bg-slate-900 text-white px-4 sm:px-6 py-3 flex items-center justify-between sticky top-0 z-40">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center"><Truck className="w-4 h-4 text-white" /></div>
          <span className="font-archivo font-bold">MediTrans</span>
          <Badge className="bg-blue-600 text-white ml-1"><Radio className="w-3 h-3 mr-1" /> Dispatch</Badge>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-300 hidden sm:block">{user?.full_name}</span>
          <span className="text-[11px] text-emerald-400 flex items-center gap-1"><span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse"></span> live</span>
          <NotificationBell dark />
          <Button variant="ghost" size="sm" className="text-white hover:bg-white/10" onClick={() => { logout(); navigate('/login'); }} data-testid="role-home-logout-btn">
            <LogOut className="w-4 h-4" />
          </Button>
        </div>
      </header>

      <main className="p-4 overflow-x-auto">
        <div className="flex items-center gap-4 mb-3 text-[11px] text-slate-500" data-testid="board-legend">
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm border-2 border-red-400 bg-white"></span> Urgent / exception</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm border-2 border-amber-400 bg-white"></span> Stale — no progress</span>
        </div>
        <div className="flex gap-3 min-w-max" data-testid="dispatch-board">
          {COLUMNS.map(([label, statuses]) => {
            const colJobs = jobs.filter((j) => statuses.includes(j.status));
            return (
              <div key={label} className="w-64 shrink-0" data-testid={`column-${label.toLowerCase().replace(' ', '-')}`}>
                <div className="flex items-center justify-between px-2 mb-2">
                  <p className="text-xs font-bold uppercase tracking-wide text-slate-500">{label}</p>
                  <Badge className="bg-slate-200 text-slate-600">{colJobs.length}</Badge>
                </div>
                <div className="space-y-2">
                  {colJobs.map((j) => {
                    const level = alertLevel(j);
                    const border = level === 'red' ? 'border-red-400' : level === 'amber' ? 'border-amber-400' : 'border-transparent';
                    return (
                      <button key={j.id} className="w-full text-left" onClick={() => openJob(j)} data-testid={`board-card-${j.id}`}>
                        <div className={`bg-white rounded-xl p-3 shadow-sm border-2 transition-shadow hover:shadow-md ${border}`}>
                          <div className="flex items-center justify-between gap-1 mb-1">
                            <p className="text-xs font-bold text-slate-900 truncate">{j.title || `Job #${j.id.slice(0, 6)}`}</p>
                            {level && <span className={`w-2 h-2 rounded-full shrink-0 ${level === 'red' ? 'bg-red-500' : 'bg-amber-500'}`}></span>}
                          </div>
                          <p className="text-[11px] text-slate-500 mb-1 truncate">{j.facility_name ? `${j.facility_name} · ` : ''}{(j.item_category || 'other').replace('_', ' ')}</p>
                          <div className="flex items-center gap-1 mb-1">
                            {(j.handling_flags || []).map((f) => {
                              const I = FLAG_ICONS[f];
                              return I ? <I key={f} className={`w-3.5 h-3.5 ${f === 'urgent' ? 'text-red-500' : 'text-slate-400'}`} title={f} /> : null;
                            })}
                          </div>
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="text-slate-600 truncate">{j.driver_name || <span className="text-slate-300">unassigned</span>}</span>
                            <span className={`flex items-center gap-0.5 shrink-0 ${level === 'red' ? 'text-red-500 font-semibold' : level === 'amber' ? 'text-amber-600 font-semibold' : 'text-slate-400'}`}>
                              <Clock className="w-3 h-3" /> {fmtMins(minsIn(j.status_since))}
                            </span>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </main>

      <Dialog open={!!selected} onOpenChange={(o) => { if (!o) setSelected(null); }}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" data-testid="dispatch-job-dialog">
          <DialogHeader>
            <DialogTitle className="font-archivo">{selected?.title || selected?.facility_name || 'Job'}</DialogTitle>
            <DialogDescription>{selected?.facility_name || 'Job details and chain of custody'}</DialogDescription>
          </DialogHeader>
          {selected && (
            <div className="space-y-4">
              <div className="text-sm text-slate-600 space-y-1">
                <div className="flex items-center gap-1.5"><span className="text-slate-400">Status:</span> <Badge className="bg-blue-100 text-blue-700">{selected.status.replace('_', ' ')}</Badge></div>
                <p><span className="text-slate-400">Route:</span> {selected.pickup_address} → {selected.delivery_address}</p>
                <p><span className="text-slate-400">Payout:</span> ${Number(selected.payout_amount ?? selected.offered_price ?? 0).toFixed(2)}{(selected.distance_km ?? selected.estimated_distance_km) != null ? ` · ${selected.distance_km ?? selected.estimated_distance_km} km` : ''}</p>
                {selected.driver_name && <p><span className="text-slate-400">Driver:</span> {selected.driver_name}</p>}
              </div>

              {!['delivered', 'completed', 'cancelled', 'returned'].includes(selected.status) && (
                <div className="bg-slate-50 rounded-xl p-3 space-y-2">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{selected.driver_name ? 'Reassign' : 'Assign'} to approved driver</p>
                  <div className="flex gap-2">
                    <select className="flex-1 h-10 rounded-md border border-slate-200 px-2 text-sm bg-white" value={assignTo} onChange={(e) => setAssignTo(e.target.value)} data-testid="assign-driver-select">
                      <option value="">Select driver…</option>
                      {drivers.map((d) => <option key={d.user_id} value={d.user_id}>{d.name}</option>)}
                    </select>
                    <Button onClick={assign} className="bg-blue-600 hover:bg-blue-700 rounded-full" data-testid="assign-driver-btn"><UserPlus className="w-4 h-4 mr-1" /> Offer</Button>
                  </div>
                  {!confirmCancel ? (
                    <Button variant="outline" size="sm" className="w-full rounded-full text-red-600 border-red-200 hover:bg-red-50" onClick={() => setConfirmCancel(true)} data-testid="dispatch-cancel-btn">
                      <XCircle className="w-4 h-4 mr-1" /> Cancel job
                    </Button>
                  ) : (
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" className="flex-1 rounded-full" onClick={() => setConfirmCancel(false)} data-testid="dispatch-cancel-abort-btn">Keep job</Button>
                      <Button size="sm" className="flex-1 rounded-full bg-red-600 hover:bg-red-700 text-white" onClick={cancelJob} data-testid="dispatch-cancel-confirm-btn">
                        <XCircle className="w-4 h-4 mr-1" /> Confirm cancel
                      </Button>
                    </div>
                  )}
                </div>
              )}

              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Chain of custody</p>
                {!events ? <p className="text-xs text-slate-400">Loading…</p> : events.length === 0 ? <p className="text-xs text-slate-400">No custody events yet.</p> : (
                  <div className="space-y-2" data-testid="dispatch-custody-timeline">
                    {events.map((ev) => (
                      <div key={ev.id} className="flex items-start gap-2 text-xs">
                        <span className="w-1.5 h-1.5 bg-blue-500 rounded-full mt-1.5 shrink-0"></span>
                        <div>
                          <p className="font-medium text-slate-800">{EVENT_LABELS[ev.event_type] || ev.event_type}</p>
                          <p className="text-slate-400">{new Date(ev.timestamp).toLocaleString('en-CA')}{ev.gps_lat != null ? ` · GPS ${ev.gps_lat.toFixed(4)}, ${ev.gps_lng.toFixed(4)}` : ''}</p>
                          {ev.recipient_name && <p className="text-slate-600">Received by {ev.recipient_name}{ev.recipient_relationship ? ` (${ev.recipient_relationship})` : ''}</p>}
                          {ev.notes && <p className="text-slate-500 italic">{ev.notes}</p>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
