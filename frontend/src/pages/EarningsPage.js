import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import {
  Truck, LogOut, Wallet, Star, MapPin, Undo2, PackageCheck,
  Navigation2, CheckCircle2, ShieldAlert, AlertCircle, FileImage, ChevronRight
} from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const EVENT_META = {
  pickup_confirmed: { icon: PackageCheck, label: 'Pickup confirmed', cls: 'text-emerald-600 bg-emerald-100' },
  in_transit_ping: { icon: Navigation2, label: 'In-transit ping', cls: 'text-blue-600 bg-blue-100' },
  delivery_attempted: { icon: ShieldAlert, label: 'Delivery attempted', cls: 'text-amber-600 bg-amber-100' },
  delivered: { icon: CheckCircle2, label: 'Delivered', cls: 'text-emerald-700 bg-emerald-100' },
  returned: { icon: Undo2, label: 'Returned to facility', cls: 'text-amber-700 bg-amber-100' },
  exception: { icon: AlertCircle, label: 'Exception', cls: 'text-red-600 bg-red-100' }
};

const fmtDate = (iso) => iso ? new Date(iso).toLocaleString('en-CA', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';

export default function EarningsPage() {
  const navigate = useNavigate();
  const { user, token, logout } = useAuth();
  const headers = { Authorization: `Bearer ${token}` };
  const [data, setData] = useState(null);
  const [custodyJob, setCustodyJob] = useState(null);
  const [custodyEvents, setCustodyEvents] = useState(null);

  const fetchEarnings = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/driver/earnings`, { headers });
      setData(r.data);
    } catch (e) {
      toast.error('Failed to load earnings');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { fetchEarnings(); }, [fetchEarnings]);

  const openCustody = async (trip) => {
    setCustodyJob(trip);
    setCustodyEvents(null);
    try {
      const r = await axios.get(`${API}/jobs/${trip.job_id}/custody-events`, { headers });
      setCustodyEvents(r.data.custody_events);
    } catch (e) {
      toast.error('Failed to load custody record');
      setCustodyJob(null);
    }
  };

  const handleLogout = () => { logout(); navigate('/'); };

  if (!data) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  const { period, lifetime, trips, cancellation_fees, commission_rate } = data;

  return (
    <div className="min-h-screen bg-slate-50">
      <nav className="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/dashboard" className="flex items-center gap-2">
              <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
                <Truck className="w-6 h-6 text-white" />
              </div>
              <span className="font-archivo font-bold text-xl text-slate-900">MediTrans</span>
            </Link>
            <div className="hidden md:flex items-center gap-1">
              <Link to="/dashboard" className="nav-link">Dashboard</Link>
              <Link to="/jobs" className="nav-link">Jobs</Link>
              <Link to="/earnings" className="nav-link active">Earnings</Link>
              <Link to="/permits" className="nav-link">Permits</Link>
              <Link to="/billing" className="nav-link">Billing</Link>
              {user?.role === 'admin' && <Link to="/admin" className="nav-link text-purple-700">Admin</Link>}
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={handleLogout} data-testid="logout-btn">
            <LogOut className="w-4 h-4 sm:mr-2" /> <span className="hidden sm:inline">Logout</span>
          </Button>
        </div>
      </nav>

      <main className="max-w-2xl lg:max-w-4xl mx-auto px-4 sm:px-6 py-6 pb-24">
        <h1 className="font-archivo font-bold text-2xl sm:text-3xl text-slate-900 mb-6">Earnings</h1>

        {/* Pay period summary */}
        <Card className="border-0 bg-slate-900 text-white mb-4" data-testid="period-summary-card">
          <CardContent className="p-5">
            <div className="flex items-center gap-2 mb-1">
              <Wallet className="w-4 h-4 text-blue-300" />
              <p className="text-xs uppercase tracking-wide text-slate-300">This pay period (from Mon {new Date(period.start).toLocaleDateString('en-CA', { month: 'short', day: 'numeric' })})</p>
            </div>
            <p className="font-archivo font-black text-4xl mb-3" data-testid="period-net">${period.net.toFixed(2)} <span className="text-base font-medium text-slate-300">net</span></p>
            <div className="grid grid-cols-3 gap-3 text-sm">
              <div><p className="text-slate-400 text-xs">Gross ({period.trip_count} trips)</p><p className="font-semibold" data-testid="period-gross">${period.gross.toFixed(2)}</p></div>
              <div><p className="text-slate-400 text-xs">Commission ({(commission_rate * 100).toFixed(0)}%)</p><p className="font-semibold text-red-300" data-testid="period-commission">−${period.commission.toFixed(2)}</p></div>
              <div><p className="text-slate-400 text-xs">Cancel fees</p><p className="font-semibold text-red-300" data-testid="period-fees">−${period.cancellation_fees.toFixed(2)}</p></div>
            </div>
          </CardContent>
        </Card>

        {/* Lifetime stats */}
        <div className="grid grid-cols-3 gap-3 mb-8" data-testid="lifetime-stats">
          <Card className="border-0 shadow-sm"><CardContent className="p-4 text-center">
            <p className="font-archivo font-bold text-2xl text-slate-900" data-testid="lifetime-trips">{lifetime.total_trips}</p>
            <p className="text-xs text-slate-500">Total trips</p>
          </CardContent></Card>
          <Card className="border-0 shadow-sm"><CardContent className="p-4 text-center">
            <p className="font-archivo font-bold text-2xl text-slate-900 flex items-center justify-center gap-1" data-testid="lifetime-rating">
              <Star className="w-5 h-5 text-amber-400 fill-amber-400" />{lifetime.rating_avg > 0 ? lifetime.rating_avg.toFixed(1) : '—'}
            </p>
            <p className="text-xs text-slate-500">{lifetime.rating_count} reviews</p>
          </CardContent></Card>
          <Card className="border-0 shadow-sm"><CardContent className="p-4 text-center">
            <p className="font-archivo font-bold text-2xl text-slate-900" data-testid="lifetime-net">${lifetime.net.toFixed(0)}</p>
            <p className="text-xs text-slate-500">Lifetime net</p>
          </CardContent></Card>
        </div>

        {/* Trip history */}
        <h2 className="font-archivo font-bold text-lg text-slate-900 mb-3">Trip History</h2>
        <p className="text-xs text-slate-500 mb-4">Tap a trip to open its read-only chain-of-custody record.</p>
        {trips.length === 0 ? (
          <Card className="border-0 shadow-sm"><CardContent className="py-12 text-center text-slate-500 text-sm">No completed trips yet.</CardContent></Card>
        ) : (
          <div className="space-y-3">
            {trips.map((t) => (
              <button key={t.job_id} className="w-full text-left" onClick={() => openCustody(t)} data-testid={`trip-row-${t.job_id}`}>
                <Card className="border-0 shadow-sm hover:shadow-md transition-shadow">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="font-semibold text-slate-900 text-sm truncate">{t.title || 'Medical transport'}</p>
                          {t.status === 'returned'
                            ? <Badge className="bg-amber-100 text-amber-700">Returned</Badge>
                            : <Badge className="bg-emerald-100 text-emerald-700">Delivered</Badge>}
                        </div>
                        <p className="text-xs text-slate-500 mt-1 flex items-center gap-1">
                          <MapPin className="w-3 h-3" /> {t.pickup_city || '—'} → {t.delivery_city || '—'} · {fmtDate(t.completed_at)}
                        </p>
                        {t.status !== 'returned' && (
                          <div className="text-xs text-slate-500 mt-2 space-y-0.5" data-testid={`trip-breakdown-${t.job_id}`}>
                            <p>Payout <span className="font-medium text-slate-700">${t.gross.toFixed(2)}</span></p>
                            <p>Platform commission ({(commission_rate * 100).toFixed(0)}%) <span className="font-medium text-red-500">−${t.commission.toFixed(2)}</span></p>
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <p className={`font-archivo font-bold text-xl ${t.status === 'returned' ? 'text-slate-400' : 'text-slate-900'}`}>
                          ${t.net.toFixed(2)}
                        </p>
                        <ChevronRight className="w-4 h-4 text-slate-300" />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </button>
            ))}
          </div>
        )}

        {/* Cancellation fees */}
        {cancellation_fees.length > 0 && (
          <div className="mt-8">
            <h2 className="font-archivo font-bold text-lg text-slate-900 mb-3">Cancellation Fees</h2>
            <div className="space-y-2" data-testid="cancellation-fees-list">
              {cancellation_fees.map((f) => (
                <Card key={f.id} className="border-0 shadow-sm">
                  <CardContent className="p-3 flex items-center justify-between">
                    <div>
                      <p className="text-sm text-slate-700">{f.description || 'Late cancellation fee'}</p>
                      <p className="text-xs text-slate-400">{fmtDate(f.created_at)} · {f.status}</p>
                    </div>
                    <p className="font-semibold text-red-500">−${Number(f.amount).toFixed(2)}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Custody record dialog */}
      <Dialog open={!!custodyJob} onOpenChange={(o) => { if (!o) { setCustodyJob(null); setCustodyEvents(null); } }}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" data-testid="custody-record-dialog">
          <DialogHeader>
            <DialogTitle className="font-archivo">Chain of Custody</DialogTitle>
          </DialogHeader>
          {custodyJob && (
            <p className="text-xs text-slate-500 -mt-2">{custodyJob.title || 'Medical transport'} · {custodyJob.pickup_city} → {custodyJob.delivery_city} · read-only record</p>
          )}
          {!custodyEvents ? (
            <div className="py-10 flex justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div></div>
          ) : custodyEvents.length === 0 ? (
            <p className="text-sm text-slate-500 py-6 text-center">No custody events recorded for this trip (legacy completion).</p>
          ) : (
            <div className="space-y-0" data-testid="custody-timeline">
              {custodyEvents.map((ev, i) => {
                const meta = EVENT_META[ev.event_type] || EVENT_META.exception;
                const Icon = meta.icon;
                return (
                  <div key={ev.id} className="flex gap-3 pb-4 relative" data-testid={`custody-event-${ev.event_type}`}>
                    {i < custodyEvents.length - 1 && <div className="absolute left-[15px] top-8 bottom-0 w-px bg-slate-200"></div>}
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${meta.cls}`}>
                      <Icon className="w-4 h-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-slate-900">{meta.label}</p>
                      <p className="text-xs text-slate-500">{fmtDate(ev.timestamp)}</p>
                      {ev.gps_lat != null && (
                        <p className="text-xs text-slate-400">GPS {ev.gps_lat.toFixed(5)}, {ev.gps_lng.toFixed(5)}</p>
                      )}
                      {ev.recipient_name && (
                        <p className="text-xs text-slate-600 mt-1">Received by <span className="font-medium">{ev.recipient_name}</span>{ev.recipient_relationship ? ` (${ev.recipient_relationship})` : ''}</p>
                      )}
                      {ev.notes && <p className="text-xs text-slate-500 italic mt-0.5">{ev.notes}</p>}
                      {ev.evidence_url && (
                        <div className="mt-2">
                          <p className="text-[11px] text-slate-400 flex items-center gap-1 mb-1"><FileImage className="w-3 h-3" /> Proof of delivery</p>
                          <img
                            src={`${process.env.REACT_APP_BACKEND_URL}${ev.evidence_url}?auth=${token}`}
                            alt="Proof of delivery evidence"
                            className="rounded-lg border border-slate-200 max-h-40 bg-white"
                            data-testid="custody-evidence-image"
                          />
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
