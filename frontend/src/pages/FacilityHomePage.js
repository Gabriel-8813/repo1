import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Truck, LogOut, Building2, Send, MapPin, AlertTriangle, Star, Navigation2, FileImage, Receipt, Download } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const CATEGORIES = [
  ['prescription', 'Prescription'], ['lab_sample', 'Lab sample'], ['biological', 'Biological'],
  ['medical_equipment', 'Medical equipment'], ['medical_supply', 'Medical supply'], ['other', 'Other']
];
const FLAGS = [
  ['cold_chain', 'Cold chain'], ['controlled_substance', 'Controlled substance'], ['fragile', 'Fragile'],
  ['urgent', 'Urgent'], ['signature_required', 'Signature required'], ['id_required', 'ID required']
];
const FACILITY_TYPES = ['pharmacy', 'clinic', 'lab', 'hospital', 'health_shop', 'other'];
const STATUS_CLS = {
  offered: 'bg-blue-100 text-blue-700', created: 'bg-slate-100 text-slate-600',
  accepted: 'bg-indigo-100 text-indigo-700', in_progress: 'bg-indigo-100 text-indigo-700',
  picked_up: 'bg-amber-100 text-amber-700', in_transit: 'bg-amber-100 text-amber-700',
  delivered: 'bg-emerald-100 text-emerald-700', completed: 'bg-emerald-100 text-emerald-700',
  returned: 'bg-red-100 text-red-700', cancelled: 'bg-red-100 text-red-700', open: 'bg-blue-100 text-blue-700'
};

const emptyForm = {
  pickup_address: '', recipient_name: '', dropoff_address: '', recipient_phone: '',
  item_count: 1, item_category: 'prescription', handling_flags: [], special_instructions: '', requested_pickup_time: ''
};

const STEPS = [['created', 'Created'], ['offered', 'Offered'], ['accepted', 'Accepted'], ['picked_up', 'Picked up'], ['in_transit', 'In transit'], ['delivered', 'Delivered']];
const STEP_INDEX = { created: 0, open: 1, offered: 1, accepted: 2, in_progress: 2, picked_up: 3, in_transit: 4, delivered: 5, completed: 5 };

const timeAgo = (iso) => {
  if (!iso) return null;
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  return m < 1 ? 'just now' : m < 60 ? `${m} min ago` : `${Math.round(m / 60)} h ago`;
};

export default function FacilityHomePage() {
  const { user, token, logout } = useAuth();
  const navigate = useNavigate();
  const headers = { Authorization: `Bearer ${token}` };

  const [facility, setFacility] = useState(undefined);
  const [deliveries, setDeliveries] = useState([]);
  const [podJob, setPodJob] = useState(null);
  const [podEvents, setPodEvents] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [setup, setSetup] = useState({ name: '', type: 'pharmacy', address: '', contact_name: '', contact_phone: '', billing_email: '' });
  const [busy, setBusy] = useState(false);
  const [billMonth, setBillMonth] = useState(new Date().toISOString().slice(0, 7));
  const [statement, setStatement] = useState(null);

  useEffect(() => {
    if (!token) return;
    axios.get(`${API}/facility/billing?month=${billMonth}`, { headers })
      .then((r) => setStatement(r.data))
      .catch(() => setStatement(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [billMonth, token, deliveries.length]);

  const exportStatement = (fmt) => {
    window.open(`${API}/facility/billing/export?month=${billMonth}&format=${fmt}&auth=${token}`, '_blank');
  };

  const load = useCallback(async () => {
    try {
      const [fr, dr] = await Promise.all([
        axios.get(`${API}/facilities`, { headers }),
        axios.get(`${API}/facility/deliveries`, { headers })
      ]);
      setFacility(fr.data.facilities[0] || null);
      setDeliveries(dr.data.deliveries);
    } catch { setFacility(null); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { load(); const iv = setInterval(load, 10000); return () => clearInterval(iv); }, [load]);

  const openPod = async (job) => {
    setPodJob(job);
    setPodEvents(null);
    try {
      const r = await axios.get(`${API}/jobs/${job.id}/custody-events`, { headers });
      setPodEvents(r.data.custody_events);
    } catch {
      toast.error('Failed to load proof of delivery');
      setPodJob(null);
    }
  };

  const toggleFlag = (f) => setForm((s) => ({
    ...s, handling_flags: s.handling_flags.includes(f) ? s.handling_flags.filter((x) => x !== f) : [...s.handling_flags, f]
  }));

  const createFacility = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await axios.post(`${API}/facilities`, { ...setup, status: 'approved' }, { headers });
      toast.success('Facility profile created');
      await load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create facility');
    } finally { setBusy(false); }
  };

  const submitRequest = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const payload = {
        ...form,
        item_count: Number(form.item_count),
        pickup_address: form.pickup_address || undefined,
        special_instructions: form.special_instructions || undefined,
        facility_id: facility.id
      };
      const r = await axios.post(`${API}/facility/requests`, payload, { headers });
      toast.success(`Request created — ${r.data.distance_km} km, driver payout $${r.data.payout_amount.toFixed(2)}. Now offered to drivers.`);
      setForm(emptyForm);
      await load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create request');
    } finally { setBusy(false); }
  };

  const handleLogout = () => { logout(); navigate('/login'); };

  if (facility === undefined) {
    return <div className="min-h-screen bg-slate-50 flex items-center justify-center"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div></div>;
  }

  return (
    <div className="min-h-screen bg-slate-50" data-testid="facility-home">
      <header className="bg-white border-b border-slate-200 px-4 sm:px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 bg-blue-600 rounded-lg flex items-center justify-center"><Truck className="w-5 h-5 text-white" /></div>
          <div>
            <span className="font-archivo font-bold text-lg text-slate-900">MediTrans</span>
            <span className="hidden sm:inline text-slate-400 text-sm ml-2">Facility Portal</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-600 hidden sm:block" data-testid="role-home-user-name">{facility?.name || user?.full_name}</span>
          <Button variant="outline" size="sm" onClick={handleLogout} data-testid="role-home-logout-btn"><LogOut className="w-4 h-4 sm:mr-1" /><span className="hidden sm:inline">Sign out</span></Button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
        {!facility ? (
          <Card className="max-w-xl mx-auto border-0 shadow-md" data-testid="facility-setup-card">
            <CardHeader><CardTitle className="font-archivo flex items-center gap-2"><Building2 className="w-5 h-5 text-blue-600" /> Set up your facility profile</CardTitle></CardHeader>
            <CardContent>
              <form onSubmit={createFacility} className="space-y-3">
                <Input required placeholder="Facility name (e.g. Queen St Pharmacy)" value={setup.name} onChange={(e) => setSetup({ ...setup, name: e.target.value })} data-testid="setup-name-input" />
                <select className="w-full h-10 rounded-md border border-slate-200 px-3 text-sm bg-white" value={setup.type} onChange={(e) => setSetup({ ...setup, type: e.target.value })} data-testid="setup-type-select">
                  {FACILITY_TYPES.map((t) => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
                </select>
                <Input required placeholder="Address (street, city, ON)" value={setup.address} onChange={(e) => setSetup({ ...setup, address: e.target.value })} data-testid="setup-address-input" />
                <div className="grid grid-cols-2 gap-3">
                  <Input required placeholder="Contact name" value={setup.contact_name} onChange={(e) => setSetup({ ...setup, contact_name: e.target.value })} data-testid="setup-contact-input" />
                  <Input required placeholder="Contact phone" value={setup.contact_phone} onChange={(e) => setSetup({ ...setup, contact_phone: e.target.value })} data-testid="setup-phone-input" />
                </div>
                <Input required type="email" placeholder="Billing email" value={setup.billing_email} onChange={(e) => setSetup({ ...setup, billing_email: e.target.value })} data-testid="setup-billing-input" />
                <Button type="submit" disabled={busy} className="w-full h-11 bg-blue-600 hover:bg-blue-700 rounded-full" data-testid="setup-submit-btn">Create facility profile</Button>
              </form>
            </CardContent>
          </Card>
        ) : (
          <Tabs defaultValue="book">
            <TabsList className="mb-6 h-11">
              <TabsTrigger value="book" className="h-9 px-6" data-testid="tab-book">Book & Track</TabsTrigger>
              <TabsTrigger value="billing" className="h-9 px-6" data-testid="tab-billing"><Receipt className="w-4 h-4 mr-1" /> Billing</TabsTrigger>
            </TabsList>

            <TabsContent value="book">
            <div className="grid lg:grid-cols-5 gap-8">
            {/* Booking form */}
            <div className="lg:col-span-3">
              <h1 className="font-archivo font-bold text-2xl text-slate-900 mb-4">Book Transport</h1>
              <Card className="border-0 shadow-md" data-testid="book-transport-form">
                <CardContent className="p-5">
                  <form onSubmit={submitRequest} className="space-y-4">
                    <div>
                      <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Pickup address</label>
                      <Input placeholder={facility.address} value={form.pickup_address} onChange={(e) => setForm({ ...form, pickup_address: e.target.value })} className="mt-1" data-testid="pickup-address-input" />
                      <p className="text-[11px] text-slate-400 mt-1">Leave blank to use your facility address: {facility.address}</p>
                    </div>
                    <div className="grid sm:grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Recipient name</label>
                        <Input required value={form.recipient_name} onChange={(e) => setForm({ ...form, recipient_name: e.target.value })} className="mt-1" data-testid="recipient-name-input" />
                      </div>
                      <div>
                        <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Recipient phone</label>
                        <Input required value={form.recipient_phone} onChange={(e) => setForm({ ...form, recipient_phone: e.target.value })} className="mt-1" data-testid="recipient-phone-input" />
                      </div>
                    </div>
                    <div>
                      <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Dropoff address</label>
                      <Input required placeholder="Street, city, ON" value={form.dropoff_address} onChange={(e) => setForm({ ...form, dropoff_address: e.target.value })} className="mt-1" data-testid="dropoff-address-input" />
                    </div>
                    <div className="grid sm:grid-cols-3 gap-3">
                      <div>
                        <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Number of items</label>
                        <Input required type="number" min="1" max="100" value={form.item_count} onChange={(e) => setForm({ ...form, item_count: e.target.value })} className="mt-1" data-testid="item-count-input" />
                      </div>
                      <div className="sm:col-span-2">
                        <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Item category</label>
                        <select className="w-full h-10 mt-1 rounded-md border border-slate-200 px-3 text-sm bg-white" value={form.item_category} onChange={(e) => setForm({ ...form, item_category: e.target.value })} data-testid="item-category-select">
                          {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                        </select>
                      </div>
                    </div>
                    <div>
                      <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Handling flags</label>
                      <div className="flex flex-wrap gap-2 mt-2" data-testid="handling-flags-group">
                        {FLAGS.map(([v, l]) => (
                          <button key={v} type="button" onClick={() => toggleFlag(v)}
                            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${form.handling_flags.includes(v) ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-600 border-slate-200 hover:border-blue-300'}`}
                            data-testid={`flag-${v}`}>{l}</button>
                        ))}
                      </div>
                    </div>
                    <div>
                      <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Non-clinical handling notes</label>
                      <p className="flex items-center gap-1 text-[11px] text-red-600 font-medium mt-0.5"><AlertTriangle className="w-3 h-3" /> Do NOT enter drug names, diagnoses, or medical details here</p>
                      <Textarea placeholder="e.g. Buzz unit 4, cooler at front desk" value={form.special_instructions} onChange={(e) => setForm({ ...form, special_instructions: e.target.value })} className="mt-1" data-testid="handling-notes-input" />
                    </div>
                    <div>
                      <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Requested pickup time</label>
                      <Input required type="datetime-local" value={form.requested_pickup_time} onChange={(e) => setForm({ ...form, requested_pickup_time: e.target.value })} className="mt-1 max-w-xs" data-testid="pickup-time-input" />
                    </div>
                    <Button type="submit" disabled={busy} className="w-full h-12 rounded-full bg-blue-600 hover:bg-blue-700 text-base font-semibold" data-testid="submit-request-btn">
                      <Send className="w-4 h-4 mr-2" /> {busy ? 'Creating…' : 'Create Request — payout auto-calculated'}
                    </Button>
                  </form>
                </CardContent>
              </Card>
            </div>

            {/* My Deliveries dashboard */}
            <div className="lg:col-span-2">
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-archivo font-bold text-2xl text-slate-900">My Deliveries</h2>
                <span className="text-[11px] text-slate-400 flex items-center gap-1"><span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse"></span> live</span>
              </div>
              {deliveries.length === 0 ? (
                <Card className="border-0 shadow-sm"><CardContent className="py-12 text-center text-slate-500 text-sm">No delivery requests yet.</CardContent></Card>
              ) : (
                <div className="space-y-3" data-testid="facility-deliveries-list">
                  {deliveries.map((j) => {
                    const idx = STEP_INDEX[j.status];
                    const isReturned = j.status === 'returned' || j.status === 'cancelled';
                    const ping = j.last_event;
                    return (
                      <Card key={j.id} className="border-0 shadow-sm" data-testid={`facility-job-${j.id}`}>
                        <CardContent className="p-4">
                          <div className="flex items-center justify-between gap-2 mb-2">
                            <p className="font-semibold text-slate-900 text-sm truncate">{j.title || 'Medical transport'}</p>
                            <Badge className={STATUS_CLS[j.status] || 'bg-slate-100 text-slate-600'} data-testid={`delivery-status-${j.id}`}>{j.status.replace('_', ' ')}</Badge>
                          </div>
                          <p className="text-xs text-slate-500 flex items-center gap-1 mb-3"><MapPin className="w-3 h-3" /> {j.delivery_address} · {j.recipient_name}</p>

                          {/* Status tracker */}
                          {!isReturned ? (
                            <div className="flex items-center gap-1 mb-3" data-testid={`delivery-tracker-${j.id}`}>
                              {STEPS.map(([key, label], i) => (
                                <div key={key} className="flex-1">
                                  <div className={`h-1.5 rounded-full ${idx >= i ? 'bg-blue-600' : 'bg-slate-200'}`}></div>
                                  <p className={`text-[9px] mt-1 text-center ${idx === i ? 'text-blue-700 font-semibold' : 'text-slate-400'}`}>{label}</p>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="text-xs text-red-600 font-medium mb-3">{j.status === 'returned' ? 'Item returned to your facility — see notifications' : 'Cancelled'}</p>
                          )}

                          {/* Driver info */}
                          {j.driver && (
                            <div className="flex items-center gap-2 bg-slate-50 rounded-lg px-3 py-2 mb-2" data-testid={`delivery-driver-${j.id}`}>
                              <div className="w-7 h-7 bg-blue-100 rounded-full flex items-center justify-center text-blue-700 text-xs font-bold">
                                {(j.driver.name || '?').charAt(0)}
                              </div>
                              <p className="text-xs font-medium text-slate-700">{j.driver.name}</p>
                              <span className="flex items-center gap-0.5 text-xs text-slate-500">
                                <Star className="w-3 h-3 text-amber-400 fill-amber-400" />
                                {j.driver.rating_avg > 0 ? j.driver.rating_avg.toFixed(1) : 'New'}{j.driver.rating_count ? ` (${j.driver.rating_count})` : ''}
                              </span>
                            </div>
                          )}

                          {/* Live location */}
                          {ping && ping.gps_lat != null && ['picked_up', 'in_transit'].includes(j.status) && (
                            <a href={`https://www.google.com/maps?q=${ping.gps_lat},${ping.gps_lng}`} target="_blank" rel="noreferrer"
                              className="flex items-center gap-1 text-xs text-blue-600 hover:underline mb-2" data-testid={`delivery-map-link-${j.id}`}>
                              <Navigation2 className="w-3 h-3" /> Driver location {timeAgo(ping.timestamp)} — view on map
                            </a>
                          )}

                          <div className="flex items-center justify-between">
                            <span className="text-xs font-semibold text-slate-800">${Number(j.payout_amount ?? j.offered_price ?? 0).toFixed(2)}</span>
                            {['delivered', 'completed'].includes(j.status) && (
                              <Button size="sm" variant="outline" className="rounded-full text-emerald-700 border-emerald-200 hover:bg-emerald-50 h-8"
                                onClick={() => openPod(j)} data-testid={`view-pod-${j.id}-btn`}>
                                <FileImage className="w-3.5 h-3.5 mr-1" /> Proof of Delivery
                              </Button>
                            )}
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
            </TabsContent>

            <TabsContent value="billing">
              <div className="max-w-3xl" data-testid="billing-tab">
                <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                  <h2 className="font-archivo font-bold text-2xl text-slate-900">Monthly Statement</h2>
                  <div className="flex items-center gap-2">
                    <Input type="month" value={billMonth} onChange={(e) => setBillMonth(e.target.value)} className="h-9 w-40" data-testid="billing-month-input" />
                    <Button size="sm" variant="outline" className="rounded-full" onClick={() => exportStatement('csv')} data-testid="export-csv-btn">
                      <Download className="w-4 h-4 mr-1" /> CSV
                    </Button>
                    <Button size="sm" variant="outline" className="rounded-full" onClick={() => exportStatement('pdf')} data-testid="export-pdf-btn">
                      <Download className="w-4 h-4 mr-1" /> PDF
                    </Button>
                  </div>
                </div>
                <p className="text-xs text-slate-500 mb-4">Delivery charges billed to your facility (separate from driver commissions).</p>
                {!statement ? (
                  <Card className="border-0 shadow-sm"><CardContent className="py-10 text-center text-slate-500 text-sm">Loading statement…</CardContent></Card>
                ) : statement.items.length === 0 ? (
                  <Card className="border-0 shadow-sm"><CardContent className="py-10 text-center text-slate-500 text-sm">No completed deliveries in {billMonth}.</CardContent></Card>
                ) : (
                  <Card className="border-0 shadow-md">
                    <CardContent className="p-0">
                      <table className="w-full text-sm" data-testid="billing-table">
                        <thead>
                          <tr className="text-left text-[11px] uppercase tracking-wide text-slate-400 border-b border-slate-100">
                            <th className="px-4 py-3">Date</th>
                            <th className="px-4 py-3">Delivery</th>
                            <th className="px-4 py-3 hidden sm:table-cell">Recipient</th>
                            <th className="px-4 py-3 text-right">Charge</th>
                          </tr>
                        </thead>
                        <tbody>
                          {statement.items.map((i) => (
                            <tr key={i.job_id} className="border-b border-slate-50" data-testid={`billing-row-${i.job_id}`}>
                              <td className="px-4 py-2.5 text-slate-500 text-xs">{new Date(i.date).toLocaleDateString('en-CA', { month: 'short', day: 'numeric' })}</td>
                              <td className="px-4 py-2.5 text-slate-800">{i.title}</td>
                              <td className="px-4 py-2.5 text-slate-500 hidden sm:table-cell">{i.recipient_name || '—'}</td>
                              <td className="px-4 py-2.5 text-right font-medium text-slate-900">${i.amount.toFixed(2)}</td>
                            </tr>
                          ))}
                        </tbody>
                        <tfoot>
                          <tr><td colSpan="3" className="px-4 py-2 text-right text-slate-500">Subtotal</td><td className="px-4 py-2 text-right font-medium" data-testid="billing-subtotal">${statement.subtotal.toFixed(2)}</td></tr>
                          <tr><td colSpan="3" className="px-4 py-2 text-right text-slate-500">HST (13%)</td><td className="px-4 py-2 text-right font-medium" data-testid="billing-hst">${statement.hst.toFixed(2)}</td></tr>
                          <tr className="border-t border-slate-200"><td colSpan="3" className="px-4 py-3 text-right font-archivo font-bold text-slate-900">Total (CAD)</td><td className="px-4 py-3 text-right font-archivo font-bold text-lg" data-testid="billing-total">${statement.total.toFixed(2)}</td></tr>
                        </tfoot>
                      </table>
                    </CardContent>
                  </Card>
                )}
              </div>
            </TabsContent>
          </Tabs>
        )}
      </main>

      {/* Proof of Delivery dialog */}
      <Dialog open={!!podJob} onOpenChange={(o) => { if (!o) { setPodJob(null); setPodEvents(null); } }}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto" data-testid="pod-dialog">
          <DialogHeader><DialogTitle className="font-archivo">Proof of Delivery</DialogTitle></DialogHeader>
          {!podEvents ? (
            <div className="py-8 flex justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div></div>
          ) : (() => {
            const del = podEvents.find((e) => e.event_type === 'delivered');
            if (!del) return <p className="text-sm text-slate-500 py-4 text-center">No delivery evidence on record (legacy completion).</p>;
            return (
              <div className="space-y-3">
                <div className="bg-slate-50 rounded-xl p-3 text-sm space-y-1">
                  <p><span className="text-slate-400 text-xs uppercase tracking-wide">Received by</span><br /><span className="font-semibold text-slate-900" data-testid="pod-recipient">{del.recipient_name}</span>{del.recipient_relationship ? <span className="text-slate-500"> ({del.recipient_relationship})</span> : null}</p>
                  <p><span className="text-slate-400 text-xs uppercase tracking-wide">Delivered at</span><br /><span className="font-medium text-slate-800" data-testid="pod-timestamp">{new Date(del.timestamp).toLocaleString('en-CA')}</span></p>
                  {del.gps_lat != null && <p className="text-xs text-slate-400">GPS {del.gps_lat.toFixed(5)}, {del.gps_lng.toFixed(5)}</p>}
                </div>
                {del.evidence_url && (
                  <div>
                    <p className="text-xs text-slate-400 mb-1">Signature / ID capture evidence</p>
                    <img src={`${process.env.REACT_APP_BACKEND_URL}${del.evidence_url}?auth=${token}`} alt="Proof of delivery evidence"
                      className="rounded-lg border border-slate-200 w-full bg-white" data-testid="pod-evidence-image" />
                  </div>
                )}
              </div>
            );
          })()}
        </DialogContent>
      </Dialog>
    </div>
  );
}
