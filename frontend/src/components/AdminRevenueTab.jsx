import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Button } from './ui/button';
import { Card, CardContent } from './ui/card';
import { Input } from './ui/input';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from './ui/table';
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle
} from './ui/dialog';
import { Download, TrendingUp, Truck, Percent, Ban, DollarSign, Eye } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmt = (n) => `$${Number(n || 0).toFixed(2)}`;

const KPI = ({ icon: Icon, label, value, testid }) => (
  <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
    <CardContent className="p-4">
      <div className="flex items-center gap-2 text-slate-500 text-xs mb-1"><Icon className="w-4 h-4" />{label}</div>
      <p className="text-2xl font-bold text-slate-900" data-testid={testid}>{value}</p>
    </CardContent>
  </Card>
);

export const AdminRevenueTab = () => {
  const { token } = useAuth();
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [summary, setSummary] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [statements, setStatements] = useState([]);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  const headers = { Authorization: `Bearer ${token}` };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, i, d] = await Promise.all([
        axios.get(`${API}/admin/billing/summary?month=${month}`, { headers }),
        axios.get(`${API}/admin/billing/invoices?month=${month}`, { headers }),
        axios.get(`${API}/admin/billing/driver-statements?month=${month}`, { headers }),
      ]);
      setSummary(s.data);
      setInvoices(i.data.invoices);
      setStatements(d.data.statements);
    } catch (e) {
      toast.error('Failed to load billing data');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, month]);

  useEffect(() => { load(); }, [load]);

  const exportCsv = (report) => {
    window.open(`${API}/admin/billing/export?month=${month}&report=${report}&auth=${token}`, '_blank');
  };

  const k = summary?.kpis;

  return (
    <div className="space-y-6" data-testid="admin-revenue-tab">
      <div className="flex flex-wrap items-center gap-3">
        <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="w-44" data-testid="revenue-month-input" />
        <Button variant="outline" size="sm" className="rounded-full" onClick={() => exportCsv('revenue')} data-testid="export-revenue-btn">
          <Download className="w-4 h-4 mr-1" /> Revenue summary CSV
        </Button>
        <Button variant="outline" size="sm" className="rounded-full" onClick={() => exportCsv('jobs')} data-testid="export-jobs-btn">
          <Download className="w-4 h-4 mr-1" /> Per-job detail CSV
        </Button>
      </div>

      {loading && !summary && (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3" data-testid="revenue-loading">
          {[...Array(5)].map((_, i) => <div key={i} className="h-24 rounded-xl bg-slate-100 animate-pulse" />)}
        </div>
      )}

      {k && (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          <KPI icon={Truck} label="Completed trips" value={k.completed_trips} testid="kpi-trips" />
          <KPI icon={DollarSign} label="Gross delivery value" value={fmt(k.gross_delivery_value)} testid="kpi-gross" />
          <KPI icon={Percent} label="Commission earned" value={fmt(k.commission_earned)} testid="kpi-commission" />
          <KPI icon={Ban} label="Cancellation fees" value={fmt(k.cancellation_fees)} testid="kpi-fees" />
          <KPI icon={TrendingUp} label="Platform revenue" value={fmt(k.platform_revenue)} testid="kpi-revenue" />
        </div>
      )}

      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
          <CardContent className="p-4">
            <p className="text-sm font-bold text-slate-900 mb-2">Revenue by facility</p>
            <Table data-testid="revenue-by-facility-table">
              <TableHeader><TableRow><TableHead>Facility</TableHead><TableHead>Trips</TableHead><TableHead>Gross</TableHead><TableHead>Commission</TableHead></TableRow></TableHeader>
              <TableBody>
                {(summary?.by_facility || []).length === 0 && <TableRow><TableCell colSpan={4} className="text-center text-slate-400 text-sm py-4">No completed trips this month.</TableCell></TableRow>}
                {(summary?.by_facility || []).map((f) => (
                  <TableRow key={f.facility_id || 'direct'}>
                    <TableCell className="text-sm">{f.name}</TableCell>
                    <TableCell className="text-sm">{f.trips}</TableCell>
                    <TableCell className="text-sm">{fmt(f.gross)}</TableCell>
                    <TableCell className="text-sm font-semibold text-emerald-700">{fmt(f.commission)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
          <CardContent className="p-4">
            <p className="text-sm font-bold text-slate-900 mb-2">Revenue by region</p>
            <Table data-testid="revenue-by-region-table">
              <TableHeader><TableRow><TableHead>Region</TableHead><TableHead>Trips</TableHead><TableHead>Gross</TableHead><TableHead>Commission</TableHead></TableRow></TableHeader>
              <TableBody>
                {(summary?.by_region || []).length === 0 && <TableRow><TableCell colSpan={4} className="text-center text-slate-400 text-sm py-4">No completed trips this month.</TableCell></TableRow>}
                {(summary?.by_region || []).map((r) => (
                  <TableRow key={r.region}>
                    <TableCell className="text-sm">{r.region}</TableCell>
                    <TableCell className="text-sm">{r.trips}</TableCell>
                    <TableCell className="text-sm">{fmt(r.gross)}</TableCell>
                    <TableCell className="text-sm font-semibold text-emerald-700">{fmt(r.commission)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-bold text-slate-900">Facility invoices — {month}</p>
            <Button variant="outline" size="sm" className="rounded-full" onClick={() => exportCsv('invoices')} data-testid="export-invoices-btn">
              <Download className="w-4 h-4 mr-1" /> CSV
            </Button>
          </div>
          <Table data-testid="invoices-table">
            <TableHeader><TableRow><TableHead>Facility</TableHead><TableHead>Deliveries</TableHead><TableHead>Subtotal</TableHead><TableHead>HST 13%</TableHead><TableHead>Invoice total</TableHead><TableHead>Commission</TableHead><TableHead></TableHead></TableRow></TableHeader>
            <TableBody>
              {invoices.length === 0 && <TableRow><TableCell colSpan={7} className="text-center text-slate-400 text-sm py-4">No invoices this month.</TableCell></TableRow>}
              {invoices.map((i) => (
                <TableRow key={i.facility_id || 'direct'} data-testid={`invoice-row-${i.facility_id || 'direct'}`}>
                  <TableCell>
                    <p className="text-sm font-semibold">{i.facility_name}</p>
                    <p className="text-xs text-slate-500">{i.billing_email}</p>
                  </TableCell>
                  <TableCell className="text-sm">{i.deliveries}</TableCell>
                  <TableCell className="text-sm">{fmt(i.subtotal)}</TableCell>
                  <TableCell className="text-sm">{fmt(i.hst)}</TableCell>
                  <TableCell className="text-sm font-semibold">{fmt(i.total)}</TableCell>
                  <TableCell className="text-sm text-emerald-700 font-semibold">{fmt(i.commission_earned)}</TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="ghost" className="h-8" onClick={() => setDetail({ type: 'invoice', data: i })} data-testid={`invoice-detail-${i.facility_id || 'direct'}-btn`}>
                      <Eye className="w-4 h-4 mr-1" /> Items
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-bold text-slate-900">Driver earnings statements — {month}</p>
            <Button variant="outline" size="sm" className="rounded-full" onClick={() => exportCsv('driver_statements')} data-testid="export-statements-btn">
              <Download className="w-4 h-4 mr-1" /> CSV
            </Button>
          </div>
          <Table data-testid="statements-table">
            <TableHeader><TableRow><TableHead>Driver</TableHead><TableHead>Trips</TableHead><TableHead>Gross</TableHead><TableHead>Commission</TableHead><TableHead>Cancel fees</TableHead><TableHead>Net payable</TableHead><TableHead></TableHead></TableRow></TableHeader>
            <TableBody>
              {statements.length === 0 && <TableRow><TableCell colSpan={7} className="text-center text-slate-400 text-sm py-4">No driver activity this month.</TableCell></TableRow>}
              {statements.map((s) => (
                <TableRow key={s.driver_id} data-testid={`statement-row-${s.driver_id}`}>
                  <TableCell>
                    <p className="text-sm font-semibold">{s.driver_name}</p>
                    <p className="text-xs text-slate-500">{s.email}</p>
                  </TableCell>
                  <TableCell className="text-sm">{s.trips}</TableCell>
                  <TableCell className="text-sm">{fmt(s.gross)}</TableCell>
                  <TableCell className="text-sm text-red-600">-{fmt(s.commission)}</TableCell>
                  <TableCell className="text-sm text-red-600">{s.cancellation_fees ? `-${fmt(s.cancellation_fees)}` : '—'}</TableCell>
                  <TableCell className="text-sm font-semibold text-emerald-700">{fmt(s.net_payable)}</TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="ghost" className="h-8" onClick={() => setDetail({ type: 'statement', data: s })} data-testid={`statement-detail-${s.driver_id}-btn`}>
                      <Eye className="w-4 h-4 mr-1" /> Items
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Dialog open={!!detail} onOpenChange={(o) => { if (!o) setDetail(null); }}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="billing-detail-dialog">
          <DialogHeader>
            <DialogTitle className="font-archivo">
              {detail?.type === 'invoice' ? `Invoice — ${detail.data.facility_name}` : `Statement — ${detail?.data.driver_name}`}
            </DialogTitle>
            <DialogDescription>{month} · line items</DialogDescription>
          </DialogHeader>
          {detail && (
            <div className="space-y-3">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead><TableHead>Delivery</TableHead>
                    {detail.type === 'invoice'
                      ? <><TableHead>Driver</TableHead><TableHead>Charge</TableHead></>
                      : <><TableHead>Gross</TableHead><TableHead>Commission</TableHead><TableHead>Net</TableHead></>}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {detail.data.items.map((l) => (
                    <TableRow key={l.job_id}>
                      <TableCell className="text-xs">{(l.date || '').slice(0, 16).replace('T', ' ')}</TableCell>
                      <TableCell className="text-xs">{l.title}</TableCell>
                      {detail.type === 'invoice'
                        ? <><TableCell className="text-xs">{l.driver_name || '—'}</TableCell><TableCell className="text-xs font-semibold">{fmt(l.facility_charge)}</TableCell></>
                        : <><TableCell className="text-xs">{fmt(l.driver_gross)}</TableCell><TableCell className="text-xs text-red-600">-{fmt(l.commission)} ({Math.round(l.commission_rate * 100)}%)</TableCell><TableCell className="text-xs font-semibold text-emerald-700">{fmt(l.driver_net)}</TableCell></>}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {detail.type === 'invoice' ? (
                <div className="text-sm text-right space-y-0.5 pr-2">
                  <p className="text-slate-500">Subtotal: <span className="font-semibold text-slate-800">{fmt(detail.data.subtotal)}</span></p>
                  <p className="text-slate-500">HST 13%: <span className="font-semibold text-slate-800">{fmt(detail.data.hst)}</span></p>
                  <p className="text-slate-900 font-bold">Total: {fmt(detail.data.total)}</p>
                </div>
              ) : (
                <div className="text-sm text-right space-y-0.5 pr-2">
                  {detail.data.fee_items.map((f) => (
                    <p key={f.id} className="text-red-600 text-xs">{f.description}: -{fmt(f.amount)}</p>
                  ))}
                  <p className="text-slate-900 font-bold">Net payable: {fmt(detail.data.net_payable)}</p>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};
