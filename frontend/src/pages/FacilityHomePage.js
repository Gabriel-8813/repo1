import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Truck, LogOut, Building2, Send, MapPin, AlertTriangle } from 'lucide-react';
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

export default function FacilityHomePage() {
  const { user, token, logout } = useAuth();
  const navigate = useNavigate();
  const headers = { Authorization: `Bearer ${token}` };

  const [facility, setFacility] = useState(undefined);
  const [jobs, setJobs] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [setup, setSetup] = useState({ name: '', type: 'pharmacy', address: '', contact_name: '', contact_phone: '', billing_email: '' });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [fr, jr] = await Promise.all([
        axios.get(`${API}/facilities`, { headers }),
        axios.get(`${API}/jobs`, { headers })
      ]);
      setFacility(fr.data.facilities[0] || null);
      setJobs(jr.data.jobs);
    } catch { setFacility(null); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { load(); const iv = setInterval(load, 20000); return () => clearInterval(iv); }, [load]);

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

            {/* Requests list */}
            <div className="lg:col-span-2">
              <h2 className="font-archivo font-bold text-2xl text-slate-900 mb-4">Your Requests</h2>
              {jobs.length === 0 ? (
                <Card className="border-0 shadow-sm"><CardContent className="py-12 text-center text-slate-500 text-sm">No delivery requests yet.</CardContent></Card>
              ) : (
                <div className="space-y-3" data-testid="facility-jobs-list">
                  {jobs.map((j) => (
                    <Card key={j.id} className="border-0 shadow-sm" data-testid={`facility-job-${j.id}`}>
                      <CardContent className="p-4">
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <p className="font-semibold text-slate-900 text-sm truncate">{j.title || 'Medical transport'}</p>
                          <Badge className={STATUS_CLS[j.status] || 'bg-slate-100 text-slate-600'}>{j.status.replace('_', ' ')}</Badge>
                        </div>
                        <p className="text-xs text-slate-500 flex items-center gap-1"><MapPin className="w-3 h-3" /> {j.delivery_address}</p>
                        <div className="flex items-center justify-between mt-2 text-xs text-slate-500">
                          <span>{j.recipient_name}{j.item_count ? ` · ${j.item_count} item${j.item_count > 1 ? 's' : ''}` : ''}</span>
                          <span className="font-semibold text-slate-800">${Number(j.payout_amount ?? j.offered_price ?? 0).toFixed(2)}</span>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
