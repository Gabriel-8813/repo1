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
import { Search, FileDown, ShieldAlert, FileWarning, Trash2, Siren, Download } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ACTION_BADGE = {
  view: 'bg-slate-100 text-slate-600',
  create: 'bg-blue-100 text-blue-700',
  update: 'bg-amber-100 text-amber-700',
  delete: 'bg-red-100 text-red-700',
  export: 'bg-violet-100 text-violet-700',
  purge: 'bg-red-600 text-white',
};

export const AdminComplianceTab = () => {
  const { token } = useAuth();
  const headers = { Authorization: `Bearer ${token}` };

  const [logs, setLogs] = useState([]);
  const [filters, setFilters] = useState({ q: '', action: '', entity: '', date_from: '', date_to: '' });
  const [missingPod, setMissingPod] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [retention, setRetention] = useState(null);
  const [retentionDays, setRetentionDays] = useState('');
  const [breachRange, setBreachRange] = useState({ date_from: '', date_to: '' });
  const [breach, setBreach] = useState(null);
  const [custodyJobId, setCustodyJobId] = useState('');
  const [loading, setLoading] = useState(true);
  const [smsData, setSmsData] = useState(null);
  const [optoutPhone, setOptoutPhone] = useState('');
  const [residency, setResidency] = useState(null);
  const [integrity, setIntegrity] = useState(null);
  const [verifying, setVerifying] = useState(false);

  const loadResidency = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/admin/compliance/residency`, { headers });
      setResidency(r.data);
    } catch { /* staff only */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const verifyIntegrity = async () => {
    setVerifying(true);
    try {
      const r = await axios.get(`${API}/admin/compliance/audit-integrity`, { headers });
      setIntegrity(r.data);
      r.data.intact ? toast.success(`Audit chain intact — ${r.data.entries_checked} entries verified`) : toast.error('Audit chain compromised!');
    } catch { toast.error('Verification failed'); }
    finally { setVerifying(false); }
  };

  const loadSms = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/admin/sms-outbox`, { headers });
      setSmsData(r.data);
    } catch { /* staff only */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const manageOptout = async (phone, action) => {
    try {
      await axios.post(`${API}/admin/sms-optouts`, { phone, action }, { headers });
      toast.success(action === 'add' ? 'Number opted out' : 'Opt-out removed');
      setOptoutPhone('');
      loadSms();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const loadLogs = useCallback(async (f) => {
    const p = new URLSearchParams();
    Object.entries(f).forEach(([k, v]) => { if (v) p.set(k, v); });
    p.set('limit', '100');
    try {
      const r = await axios.get(`${API}/audit-logs?${p.toString()}`, { headers });
      setLogs(r.data.logs);
    } catch { toast.error('Failed to load audit log'); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [m, a, r] = await Promise.all([
        axios.get(`${API}/admin/compliance/missing-pod`, { headers }),
        axios.get(`${API}/admin/compliance/credential-alerts`, { headers }),
        axios.get(`${API}/admin/compliance/retention`, { headers }),
      ]);
      setMissingPod(m.data.jobs);
      setAlerts(a.data.alerts);
      setRetention(r.data);
      setRetentionDays(String(r.data.retention_days));
    } catch { toast.error('Failed to load compliance data'); }
    finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { loadAll(); loadLogs(filters); loadSms(); loadResidency(); }, [loadAll, loadSms, loadResidency]); // eslint-disable-line react-hooks/exhaustive-deps

  const saveRetention = async () => {
    try {
      await axios.put(`${API}/admin/compliance/retention`, { retention_days: Number(retentionDays) }, { headers });
      toast.success('Retention period updated');
      loadAll();
    } catch (e) { toast.error(e.response?.data?.detail?.[0]?.msg || e.response?.data?.detail || 'Update failed'); }
  };

  const runPurge = async () => {
    try {
      const r = await axios.post(`${API}/admin/compliance/purge`, {}, { headers });
      toast.success(`Purge complete — ${r.data.purged_jobs} job(s) redacted`);
      loadAll();
      loadLogs(filters);
    } catch { toast.error('Purge failed'); }
  };

  const compileBreach = async () => {
    if (!breachRange.date_from || !breachRange.date_to) { toast.error('Pick both dates'); return; }
    try {
      const r = await axios.get(`${API}/admin/compliance/breach-report?date_from=${breachRange.date_from}&date_to=${breachRange.date_to}`, { headers });
      setBreach(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed to compile report'); }
  };

  const exportCustody = (jobId) => {
    if (!jobId) { toast.error('Enter a job ID'); return; }
    window.open(`${API}/jobs/${jobId}/custody-record/pdf?auth=${token}`, '_blank');
  };

  return (
    <div className="space-y-6" data-testid="admin-compliance-tab">
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="compliance-loading">
          {[...Array(3)].map((_, i) => <div key={i} className="h-20 rounded-xl bg-slate-100 animate-pulse" />)}
        </div>
      ) : (
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
          <CardContent className="p-4 flex items-center gap-3">
            <FileWarning className={`w-8 h-8 ${missingPod.length ? 'text-red-500' : 'text-emerald-500'}`} />
            <div>
              <p className="text-2xl font-bold" data-testid="missing-pod-count">{missingPod.length}</p>
              <p className="text-xs text-slate-500">Jobs missing proof-of-delivery</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
          <CardContent className="p-4 flex items-center gap-3">
            <ShieldAlert className={`w-8 h-8 ${alerts.length ? 'text-amber-500' : 'text-emerald-500'}`} />
            <div>
              <p className="text-2xl font-bold" data-testid="credential-alerts-count">{alerts.length}</p>
              <p className="text-xs text-slate-500">Expired-credential alerts</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
          <CardContent className="p-4 flex items-center gap-3">
            <Trash2 className="w-8 h-8 text-slate-400" />
            <div>
              <p className="text-2xl font-bold" data-testid="retention-days-display">{retention?.retention_days ?? '—'}d</p>
              <p className="text-xs text-slate-500">
                Retention · last purge {retention?.last_purge ? `${retention.last_purge.ran_at.slice(0, 10)} (${retention.last_purge.purged_jobs} jobs)` : 'never'}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
      )}

      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
          <CardContent className="p-4 space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-sm font-bold text-slate-900">Data residency & encryption</p>
              <Badge className="bg-blue-50 text-blue-700 border border-blue-200 font-semibold" data-testid="residency-region-badge">🍁 {residency?.configured_region || '—'}</Badge>
            </div>
            <div className="space-y-1.5" data-testid="residency-components">
              {(residency?.components || []).map((c) => (
                <div key={c.name} className="flex items-center justify-between bg-slate-50 rounded-lg px-3 py-1.5">
                  <span className="text-xs text-slate-700">{c.name}</span>
                  <Badge className="bg-slate-100 text-slate-600 text-[10px]">{c.region}</Badge>
                </div>
              ))}
            </div>
            {residency && (
              <div className="text-[11px] text-slate-500 space-y-0.5">
                <p>At rest: {residency.encryption.at_rest}</p>
                <p>In transit: {residency.encryption.in_transit}</p>
                <p className="text-slate-400 italic">{residency.attestation}</p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
          <CardContent className="p-4 space-y-3">
            <p className="text-sm font-bold text-slate-900">Audit log integrity</p>
            <p className="text-xs text-slate-500">The audit log is append-only with a SHA-256 hash chain — no role can edit or delete entries. Verification recomputes every hash and detects any tampering or deletion.</p>
            <Button size="sm" className="rounded-full bg-blue-600 hover:bg-blue-700" onClick={verifyIntegrity} disabled={verifying} data-testid="verify-integrity-btn">
              {verifying ? 'Verifying…' : 'Verify integrity now'}
            </Button>
            {integrity && (
              <div className={`rounded-lg px-3 py-2 text-xs ${integrity.intact ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'}`} data-testid="integrity-result">
                {integrity.intact
                  ? `✓ Chain intact — ${integrity.entries_checked} entries verified at ${(integrity.verified_at || '').slice(11, 19)} UTC`
                  : `✗ ${integrity.problem}`}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
        <CardContent className="p-4">
          <p className="text-sm font-bold text-slate-900 mb-3">Audit log</p>
          <div className="flex flex-wrap items-end gap-2 mb-3">
            <div className="flex-1 min-w-[180px]">
              <Label className="text-xs">Search (user, job ID, entity)</Label>
              <Input value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} placeholder="e.g. dispatcher1@ or job id" data-testid="audit-search-input" />
            </div>
            <div>
              <Label className="text-xs">Action</Label>
              <select className="h-10 rounded-md border border-slate-200 px-2 text-sm bg-white" value={filters.action} onChange={(e) => setFilters({ ...filters, action: e.target.value })} data-testid="audit-action-select">
                <option value="">All</option>
                {['view', 'create', 'update', 'delete', 'export', 'purge'].map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-xs">From</Label>
              <Input type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} data-testid="audit-date-from" />
            </div>
            <div>
              <Label className="text-xs">To</Label>
              <Input type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} data-testid="audit-date-to" />
            </div>
            <Button size="sm" className="rounded-full bg-blue-600 hover:bg-blue-700" onClick={() => loadLogs(filters)} data-testid="audit-search-btn">
              <Search className="w-4 h-4 mr-1" /> Search
            </Button>
          </div>
          <div className="max-h-80 overflow-y-auto">
            <Table data-testid="audit-log-table">
              <TableHeader><TableRow><TableHead>Time (UTC)</TableHead><TableHead>Actor</TableHead><TableHead>Action</TableHead><TableHead>Entity</TableHead><TableHead>Details</TableHead></TableRow></TableHeader>
              <TableBody>
                {logs.length === 0 && <TableRow><TableCell colSpan={5} className="text-center text-slate-400 text-sm py-4">No matching entries.</TableCell></TableRow>}
                {logs.map((l) => (
                  <TableRow key={l.id}>
                    <TableCell className="text-xs whitespace-nowrap">{(l.timestamp || '').slice(0, 19).replace('T', ' ')}</TableCell>
                    <TableCell className="text-xs">
                      <p className="font-medium">{l.actor_name || l.actor_id?.slice(0, 8)}</p>
                      <p className="text-slate-400">{l.actor_email} · {l.actor_role}</p>
                    </TableCell>
                    <TableCell><Badge className={`${ACTION_BADGE[l.action] || 'bg-slate-100 text-slate-600'} text-[10px]`}>{l.action}</Badge></TableCell>
                    <TableCell className="text-xs">{l.entity}<p className="text-slate-400 font-mono text-[10px]">{(l.entity_id || '').slice(0, 12)}</p></TableCell>
                    <TableCell className="text-[10px] text-slate-500 max-w-[220px] truncate">{l.details ? JSON.stringify(l.details) : '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
          <CardContent className="p-4">
            <p className="text-sm font-bold text-slate-900 mb-2">Missing proof-of-delivery</p>
            <div className="max-h-64 overflow-y-auto">
              <Table data-testid="missing-pod-table">
                <TableHeader><TableRow><TableHead>Delivery</TableHead><TableHead>Driver</TableHead><TableHead>Issue</TableHead><TableHead></TableHead></TableRow></TableHeader>
                <TableBody>
                  {missingPod.length === 0 && <TableRow><TableCell colSpan={4} className="text-center text-emerald-600 text-sm py-4">All delivered jobs have proof-of-delivery.</TableCell></TableRow>}
                  {missingPod.map((j) => (
                    <TableRow key={j.job_id} className="bg-red-50/60" data-testid={`missing-pod-row-${j.job_id}`}>
                      <TableCell className="text-xs">
                        <p className="font-semibold">{j.title}</p>
                        <p className="text-slate-500">{j.facility_name} · {(j.delivered_at || '').slice(0, 10)}</p>
                      </TableCell>
                      <TableCell className="text-xs">{j.driver_name || '—'}</TableCell>
                      <TableCell><Badge className="bg-red-100 text-red-700 text-[10px]">{j.issue === 'no_delivered_event' ? 'No delivered event' : 'No signature'}</Badge></TableCell>
                      <TableCell className="text-right">
                        <Button size="sm" variant="ghost" className="h-7" onClick={() => exportCustody(j.job_id)} title="Export custody record PDF" data-testid={`export-custody-${j.job_id}-btn`}>
                          <FileDown className="w-4 h-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
          <CardContent className="p-4">
            <p className="text-sm font-bold text-slate-900 mb-2">Expired-credential alerts</p>
            <div className="max-h-64 overflow-y-auto">
              <Table data-testid="credential-alerts-table">
                <TableHeader><TableRow><TableHead>Driver</TableHead><TableHead>Status</TableHead><TableHead>Issues</TableHead></TableRow></TableHeader>
                <TableBody>
                  {alerts.length === 0 && <TableRow><TableCell colSpan={3} className="text-center text-emerald-600 text-sm py-4">No credential issues.</TableCell></TableRow>}
                  {alerts.map((a) => (
                    <TableRow key={a.user_id} className="bg-amber-50/60" data-testid={`credential-alert-row-${a.user_id}`}>
                      <TableCell className="text-xs"><p className="font-semibold">{a.driver_name}</p><p className="text-slate-500">{a.email}</p></TableCell>
                      <TableCell><Badge className="bg-slate-100 text-slate-600 text-[10px]">{a.verification_status}</Badge></TableCell>
                      <TableCell className="text-xs space-y-0.5">
                        {a.issues.map((i) => (
                          <Badge key={i.type} className={`${i.type === 'insurance_expired' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'} text-[10px] mr-1`}>{i.detail}</Badge>
                        ))}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
          <CardContent className="p-4 space-y-3">
            <p className="text-sm font-bold text-slate-900">Chain-of-custody export</p>
            <p className="text-xs text-slate-500">Full PDF record of a job — details, custody events, access history. For facility requests or regulators.</p>
            <div className="flex gap-2">
              <Input placeholder="Job ID" value={custodyJobId} onChange={(e) => setCustodyJobId(e.target.value)} data-testid="custody-jobid-input" />
              <Button size="sm" className="rounded-full bg-blue-600 hover:bg-blue-700 shrink-0" onClick={() => exportCustody(custodyJobId.trim())} data-testid="custody-export-btn">
                <FileDown className="w-4 h-4 mr-1" /> PDF
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
          <CardContent className="p-4 space-y-3">
            <p className="text-sm font-bold text-slate-900">Data retention</p>
            <p className="text-xs text-slate-500">Recipient names, phones and signature evidence are auto-redacted from jobs older than this (runs daily).</p>
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <Label className="text-xs">Retention period (days)</Label>
                <Input type="number" min="30" max="3650" value={retentionDays} onChange={(e) => setRetentionDays(e.target.value)} data-testid="retention-days-input" />
              </div>
              <Button size="sm" variant="outline" className="rounded-full" onClick={saveRetention} data-testid="retention-save-btn">Save</Button>
            </div>
            <Button size="sm" variant="outline" className="rounded-full w-full text-red-600 border-red-200 hover:bg-red-50" onClick={runPurge} data-testid="run-purge-btn">
              <Trash2 className="w-4 h-4 mr-1" /> Run purge now
            </Button>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
          <CardContent className="p-4 space-y-3">
            <p className="text-sm font-bold text-slate-900 flex items-center gap-1.5"><Siren className="w-4 h-4 text-red-500" /> Breach-report helper</p>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">From</Label>
                <Input type="date" value={breachRange.date_from} onChange={(e) => setBreachRange({ ...breachRange, date_from: e.target.value })} data-testid="breach-date-from" />
              </div>
              <div>
                <Label className="text-xs">To</Label>
                <Input type="date" value={breachRange.date_to} onChange={(e) => setBreachRange({ ...breachRange, date_to: e.target.value })} data-testid="breach-date-to" />
              </div>
            </div>
            <div className="flex gap-2">
              <Button size="sm" className="rounded-full bg-blue-600 hover:bg-blue-700 flex-1" onClick={compileBreach} data-testid="breach-compile-btn">Compile</Button>
              {breach && (
                <Button size="sm" variant="outline" className="rounded-full" onClick={() => window.open(`${API}/admin/compliance/breach-report?date_from=${breachRange.date_from}&date_to=${breachRange.date_to}&format=csv&auth=${token}`, '_blank')} data-testid="breach-csv-btn">
                  <Download className="w-4 h-4" />
                </Button>
              )}
            </div>
            {breach && (
              <div className="bg-slate-50 rounded-lg p-3 text-xs space-y-1" data-testid="breach-summary">
                <p><span className="font-semibold">{breach.summary.affected_jobs}</span> affected jobs · <span className="font-semibold">{breach.summary.jobs_with_personal_data}</span> with personal data</p>
                <p>{breach.summary.unique_recipients} recipient{breach.summary.unique_recipients === 1 ? '' : 's'} · {breach.summary.drivers_involved} driver{breach.summary.drivers_involved === 1 ? '' : 's'} · {breach.summary.facilities_involved} facilit{breach.summary.facilities_involved === 1 ? 'y' : 'ies'}</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)] lg:col-span-2">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-bold text-slate-900">SMS outbox (CASL)</p>
              <Badge className={smsData?.twilio_configured ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'} data-testid="twilio-mode-badge">
                {smsData?.twilio_configured ? 'Twilio live' : 'Dev mode — messages stored, not sent'}
              </Badge>
            </div>
            <div className="max-h-72 overflow-y-auto">
              <Table data-testid="sms-outbox-table">
                <TableHeader><TableRow><TableHead>Time</TableHead><TableHead>To</TableHead><TableHead>Type</TableHead><TableHead>Message</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
                <TableBody>
                  {(!smsData || smsData.messages.length === 0) && <TableRow><TableCell colSpan={5} className="text-center text-slate-400 text-sm py-4">No SMS messages yet.</TableCell></TableRow>}
                  {(smsData?.messages || []).map((m) => (
                    <TableRow key={m.id} data-testid={`sms-row-${m.id}`}>
                      <TableCell className="text-xs whitespace-nowrap">{(m.created_at || '').slice(5, 16).replace('T', ' ')}</TableCell>
                      <TableCell className="text-xs font-mono">{m.to_phone}</TableCell>
                      <TableCell><Badge className="bg-slate-100 text-slate-600 text-[10px]">{m.kind}</Badge></TableCell>
                      <TableCell className="text-[11px] text-slate-600 max-w-[260px] truncate" title={m.body}>{m.body}</TableCell>
                      <TableCell>
                        <Badge className={`text-[10px] ${m.status === 'sent' ? 'bg-emerald-100 text-emerald-700' : m.status === 'dev_outbox' ? 'bg-blue-100 text-blue-700' : 'bg-red-100 text-red-700'}`}>{m.status}</Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
          <CardContent className="p-4 space-y-3">
            <p className="text-sm font-bold text-slate-900">SMS opt-outs</p>
            <p className="text-xs text-slate-500">Numbers that replied STOP (or were added here) never receive SMS.</p>
            <div className="flex gap-2">
              <Input placeholder="+14165551234" value={optoutPhone} onChange={(e) => setOptoutPhone(e.target.value)} data-testid="optout-phone-input" />
              <Button size="sm" variant="outline" className="rounded-full shrink-0" onClick={() => manageOptout(optoutPhone, 'add')} data-testid="optout-add-btn">Opt out</Button>
            </div>
            <div className="max-h-48 overflow-y-auto space-y-1" data-testid="optout-list">
              {(smsData?.optouts || []).length === 0 && <p className="text-xs text-slate-400">No opt-outs.</p>}
              {(smsData?.optouts || []).map((o) => (
                <div key={o.phone} className="flex items-center justify-between bg-slate-50 rounded-lg px-3 py-1.5">
                  <span className="text-xs font-mono">{o.phone} <span className="text-slate-400">({o.source})</span></span>
                  <Button size="sm" variant="ghost" className="h-6 text-xs text-blue-600" onClick={() => manageOptout(o.phone, 'remove')} data-testid={`optout-remove-${o.phone}`}>Remove</Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
