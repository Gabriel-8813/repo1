import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Button } from './ui/button';
import { Card, CardContent } from './ui/card';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Label } from './ui/label';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from './ui/table';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle
} from './ui/dialog';
import { Building2, Pencil, ShieldCheck, ShieldOff, Percent, DollarSign } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STATUS_BADGE = {
  pending: 'bg-amber-100 text-amber-700',
  approved: 'bg-emerald-100 text-emerald-700',
  suspended: 'bg-red-600 text-white',
};

const FACILITY_TYPES = ['pharmacy', 'clinic', 'lab', 'hospital', 'health_shop', 'other'];

export const FacilityManagementTab = () => {
  const { token } = useAuth();
  const [facilities, setFacilities] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({});

  const headers = { Authorization: `Bearer ${token}` };

  const fetchFacilities = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/facilities`, { headers });
      setFacilities(res.data.facilities);
    } catch (e) {
      toast.error('Failed to load facilities');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { fetchFacilities(); }, [fetchFacilities]);

  const setStatus = async (facilityId, status) => {
    try {
      await axios.put(`${API}/facilities/${facilityId}`, { status }, { headers });
      toast.success(`Facility ${status}`);
      fetchFacilities();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Update failed');
    }
  };

  const openEdit = (f) => {
    setForm({
      name: f.name || '', type: f.type || 'other', address: f.address || '',
      contact_name: f.contact_name || '', contact_phone: f.contact_phone || '',
      billing_email: f.billing_email || '',
      per_delivery_rate: f.per_delivery_rate ?? '',
      commission_rate_override: f.commission_rate_override != null ? Math.round(f.commission_rate_override * 100) : '',
    });
    setEditing(f);
  };

  const saveEdit = async () => {
    const payload = {
      name: form.name, type: form.type, address: form.address,
      contact_name: form.contact_name, contact_phone: form.contact_phone,
      billing_email: form.billing_email,
      per_delivery_rate: form.per_delivery_rate === '' ? null : Number(form.per_delivery_rate),
      commission_rate_override: form.commission_rate_override === '' ? null : Number(form.commission_rate_override) / 100,
    };
    try {
      await axios.put(`${API}/facilities/${editing.id}`, payload, { headers });
      toast.success('Facility updated');
      setEditing(null);
      fetchFacilities();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Save failed');
    }
  };

  const terms = (f) => {
    const chips = [];
    if (f.per_delivery_rate != null) {
      chips.push(
        <span key="rate" className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold bg-blue-100 text-blue-700" data-testid={`terms-rate-${f.id}`}>
          <DollarSign className="w-3 h-3 mr-0.5" />{Number(f.per_delivery_rate).toFixed(2)}/delivery
        </span>
      );
    }
    if (f.commission_rate_override != null) {
      chips.push(
        <span key="comm" className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold bg-violet-100 text-violet-700" data-testid={`terms-commission-${f.id}`}>
          <Percent className="w-3 h-3 mr-0.5" />{Math.round(f.commission_rate_override * 100)}% commission
        </span>
      );
    }
    return chips.length ? <div className="flex flex-wrap gap-1">{chips}</div> : <span className="text-[11px] text-slate-400">Global terms</span>;
  };

  return (
    <div className="space-y-4" data-testid="facility-management-tab">
      <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
        <CardContent className="p-0">
          <Table data-testid="facility-mgmt-table">
            <TableHeader>
              <TableRow>
                <TableHead>Facility</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Contact</TableHead>
                <TableHead>Volume</TableHead>
                <TableHead>Terms</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {facilities.length === 0 && (
                <TableRow><TableCell colSpan={7} className="text-center text-slate-500 text-sm py-8">No facilities yet.</TableCell></TableRow>
              )}
              {facilities.map((f) => (
                <TableRow key={f.id} className={f.status === 'suspended' ? 'bg-red-50/70 hover:bg-red-50' : ''} data-testid={`facility-row-${f.id}`}>
                  <TableCell>
                    <p className="font-semibold text-slate-900 text-sm flex items-center gap-1.5"><Building2 className="w-3.5 h-3.5 text-slate-400" />{f.name}</p>
                    <p className="text-xs text-slate-500">{f.address}</p>
                  </TableCell>
                  <TableCell><Badge className="bg-slate-100 text-slate-600 capitalize">{(f.type || 'other').replace('_', ' ')}</Badge></TableCell>
                  <TableCell>
                    <p className="text-xs text-slate-700">{f.contact_name}{f.contact_phone ? ` · ${f.contact_phone}` : ''}</p>
                    <p className="text-xs text-slate-500">{f.billing_email}</p>
                    {f.owner && <p className="text-[10px] text-slate-400">Owner: {f.owner.full_name} ({f.owner.email})</p>}
                  </TableCell>
                  <TableCell data-testid={`facility-volume-${f.id}`}>
                    <p className="text-sm text-slate-800 font-semibold">{f.volume.delivered_jobs}<span className="text-slate-400 font-normal">/{f.volume.total_jobs} delivered</span></p>
                    <p className="text-[11px] text-slate-500">{f.volume.last_30d_jobs} in 30d · ${f.volume.total_billed.toFixed(2)} billed</p>
                  </TableCell>
                  <TableCell>{terms(f)}</TableCell>
                  <TableCell>
                    <Badge className={STATUS_BADGE[f.status] || STATUS_BADGE.pending} data-testid={`facility-status-${f.id}`}>{f.status}</Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      {f.status !== 'approved' && (
                        <Button size="sm" className="rounded-full bg-emerald-600 hover:bg-emerald-700 h-8" onClick={() => setStatus(f.id, 'approved')} data-testid={`approve-facility-${f.id}-btn`}>
                          <ShieldCheck className="w-4 h-4 mr-1" /> Approve
                        </Button>
                      )}
                      {f.status !== 'suspended' && (
                        <Button size="sm" variant="outline" className="rounded-full text-red-600 border-red-200 hover:bg-red-50 h-8" onClick={() => setStatus(f.id, 'suspended')} data-testid={`suspend-facility-${f.id}-btn`}>
                          <ShieldOff className="w-4 h-4 mr-1" /> Suspend
                        </Button>
                      )}
                      <Button size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={() => openEdit(f)} title="Edit facility" data-testid={`edit-facility-${f.id}-btn`}>
                        <Pencil className="w-4 h-4 text-slate-500" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Dialog open={!!editing} onOpenChange={(o) => { if (!o) setEditing(null); }}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" data-testid="facility-edit-dialog">
          <DialogHeader>
            <DialogTitle className="font-archivo">Edit facility</DialogTitle>
            <DialogDescription>Details and per-facility pricing terms. Leave pricing blank to use global terms.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Name</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="facility-edit-name" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Type</Label>
                <select className="w-full h-10 rounded-md border border-slate-200 px-2 text-sm bg-white" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} data-testid="facility-edit-type">
                  {FACILITY_TYPES.map((t) => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
                </select>
              </div>
              <div>
                <Label className="text-xs">Billing email</Label>
                <Input type="email" value={form.billing_email} onChange={(e) => setForm({ ...form, billing_email: e.target.value })} data-testid="facility-edit-billing-email" />
              </div>
            </div>
            <div>
              <Label className="text-xs">Address</Label>
              <Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} data-testid="facility-edit-address" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Contact name</Label>
                <Input value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} data-testid="facility-edit-contact-name" />
              </div>
              <div>
                <Label className="text-xs">Contact phone</Label>
                <Input value={form.contact_phone} onChange={(e) => setForm({ ...form, contact_phone: e.target.value })} data-testid="facility-edit-contact-phone" />
              </div>
            </div>
            <div className="bg-slate-50 rounded-xl p-3 space-y-3">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Pricing terms</p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Flat rate per delivery (CAD)</Label>
                  <Input type="number" min="0" step="0.01" placeholder="Global ($1.50/km)" value={form.per_delivery_rate} onChange={(e) => setForm({ ...form, per_delivery_rate: e.target.value })} data-testid="facility-edit-rate" />
                </div>
                <div>
                  <Label className="text-xs">Commission override (%)</Label>
                  <Input type="number" min="0" max="100" step="1" placeholder="Global (20%)" value={form.commission_rate_override} onChange={(e) => setForm({ ...form, commission_rate_override: e.target.value })} data-testid="facility-edit-commission" />
                </div>
              </div>
              <p className="text-[11px] text-slate-400">Flat rate replaces the distance-based price; urgent (×1.5) and cold-chain (+$15) surcharges still apply.</p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button className="bg-blue-600 hover:bg-blue-700" onClick={saveEdit} data-testid="facility-edit-save-btn">Save changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
