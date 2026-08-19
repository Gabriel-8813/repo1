import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Button } from './ui/button';
import { Card, CardContent } from './ui/card';
import { Badge } from './ui/badge';
import { Textarea } from './ui/textarea';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from './ui/table';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle
} from './ui/dialog';
import { Eye, Check, X, ShieldCheck, ShieldOff, Snowflake, Star, AlertTriangle, RotateCcw } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const VERIF_BADGE = {
  incomplete: 'bg-slate-100 text-slate-600',
  pending_review: 'bg-amber-100 text-amber-700',
  approved: 'bg-emerald-100 text-emerald-700',
  rejected: 'bg-red-100 text-red-700',
  suspended: 'bg-red-600 text-white',
};

const DOC_BADGE = {
  missing: 'bg-slate-100 text-slate-500',
  pending: 'bg-amber-100 text-amber-700',
  approved: 'bg-emerald-100 text-emerald-700',
  rejected: 'bg-red-100 text-red-700',
};

const CRED_BADGE = {
  valid: 'bg-emerald-100 text-emerald-700',
  pending: 'bg-amber-100 text-amber-700',
  rejected: 'bg-red-100 text-red-700',
  expired: 'bg-red-100 text-red-700',
  not_submitted: 'bg-slate-100 text-slate-400',
};

const CredChip = ({ label, status, testid }) => (
  <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${CRED_BADGE[status] || CRED_BADGE.not_submitted}`} title={`${label}: ${status.replace('_', ' ')}`} data-testid={testid}>
    {label}
  </span>
);

export const DriverVerificationTab = () => {
  const { token } = useAuth();
  const [drivers, setDrivers] = useState([]);
  const [selected, setSelected] = useState(null);
  const [rejectTarget, setRejectTarget] = useState(null);
  const [rejectNotes, setRejectNotes] = useState('');

  const headers = { Authorization: `Bearer ${token}` };

  const fetchDrivers = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/driver-verifications`, { headers });
      setDrivers(res.data.drivers);
      setSelected((prev) => prev ? (res.data.drivers.find((d) => d.user_id === prev.user_id) || null) : prev);
    } catch (e) {
      toast.error('Failed to load drivers');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { fetchDrivers(); }, [fetchDrivers]);

  const reviewDoc = async (docId, status, notes) => {
    try {
      await axios.put(`${API}/admin/driver-documents/${docId}`, { status, review_notes: notes || null }, { headers });
      toast.success(`Document ${status}`);
      fetchDrivers();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Review failed');
    }
  };

  const setVerification = async (userId, verification_status) => {
    try {
      await axios.put(`${API}/admin/driver-verifications/${userId}`, { verification_status }, { headers });
      toast.success(`Driver ${verification_status.replace('_', ' ')}`);
      fetchDrivers();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Update failed');
    }
  };

  const viewDoc = (docId) => {
    window.open(`${API}/driver-documents/${docId}/file?auth=${token}`, '_blank');
  };

  const confirmReject = async () => {
    if (!rejectTarget) return;
    await reviewDoc(rejectTarget, 'rejected', rejectNotes);
    setRejectTarget(null);
    setRejectNotes('');
  };

  const insuranceFlag = (d) => {
    if (d.insurance_flag === 'expired') {
      return <Badge className="bg-red-100 text-red-700" data-testid={`insurance-flag-${d.user_id}`}><AlertTriangle className="w-3 h-3 mr-1" />Insurance expired</Badge>;
    }
    if (d.insurance_flag === 'expiring_soon') {
      return <Badge className="bg-amber-100 text-amber-700" data-testid={`insurance-flag-${d.user_id}`}><AlertTriangle className="w-3 h-3 mr-1" />Expires soon</Badge>;
    }
    return null;
  };

  return (
    <div className="space-y-4" data-testid="driver-verification-tab">
      <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
        <CardContent className="p-0">
          <Table data-testid="driver-mgmt-table">
            <TableHeader>
              <TableRow>
                <TableHead>Driver</TableHead>
                <TableHead>Credentials</TableHead>
                <TableHead>Insurance expiry</TableHead>
                <TableHead>Rating</TableHead>
                <TableHead>Trips</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {drivers.length === 0 && (
                <TableRow><TableCell colSpan={7} className="text-center text-slate-500 text-sm py-8">No driver records yet.</TableCell></TableRow>
              )}
              {drivers.map((d) => (
                <TableRow
                  key={d.user_id}
                  className={d.insurance_flag === 'expired' ? 'bg-red-50/70 hover:bg-red-50' : d.insurance_flag === 'expiring_soon' ? 'bg-amber-50/70 hover:bg-amber-50' : ''}
                  data-testid={`driver-verification-row-${d.user_id}`}
                >
                  <TableCell>
                    <p className="font-semibold text-slate-900 text-sm">{d.full_name}</p>
                    <p className="text-xs text-slate-500">{d.email}</p>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap items-center gap-1 max-w-[220px]">
                      <CredChip label="CVOR" status={d.cvor_status} testid={`cred-cvor-${d.user_id}`} />
                      <CredChip label="TDG" status={d.tdg_cert_status} testid={`cred-tdg-${d.user_id}`} />
                      <CredChip label="VSC" status={d.vulnerable_sector_check_status} testid={`cred-vsc-${d.user_id}`} />
                      <CredChip label="INS" status={d.insurance_flag === 'expired' ? 'expired' : d.insurance_status} testid={`cred-ins-${d.user_id}`} />
                      {d.cold_chain_certified && (
                        <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold bg-blue-100 text-blue-700" title="Cold-chain certified" data-testid={`cred-cold-${d.user_id}`}>
                          <Snowflake className="w-3 h-3 mr-0.5" />COLD
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <p className="text-xs text-slate-600">{d.insurance_expiry || '—'}</p>
                    {insuranceFlag(d)}
                  </TableCell>
                  <TableCell>
                    <span className="flex items-center gap-1 text-sm text-slate-700" data-testid={`driver-rating-${d.user_id}`}>
                      <Star className="w-3.5 h-3.5 text-amber-400 fill-amber-400" />
                      {Number(d.rating_avg || 0).toFixed(1)}
                      <span className="text-[10px] text-slate-400">({d.rating_count})</span>
                    </span>
                  </TableCell>
                  <TableCell className="text-sm text-slate-700" data-testid={`driver-trips-${d.user_id}`}>{d.total_trips}</TableCell>
                  <TableCell>
                    <Badge className={VERIF_BADGE[d.verification_status] || VERIF_BADGE.incomplete} data-testid={`verification-badge-${d.user_id}`}>
                      {d.verification_status.replace('_', ' ')}
                    </Badge>
                    {!d.compliant && d.verification_status === 'approved' && (
                      <p className="text-[10px] text-red-600 font-semibold mt-0.5">blocked from new jobs</p>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="outline" className="rounded-full" onClick={() => setSelected(d)} data-testid={`review-driver-${d.user_id}-btn`}>
                      <Eye className="w-4 h-4 mr-1" /> Review
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Dialog open={!!selected} onOpenChange={(o) => { if (!o) setSelected(null); }}>
        <DialogContent className="max-w-xl max-h-[85vh] overflow-y-auto" data-testid="driver-detail-dialog">
          <DialogHeader>
            <DialogTitle className="font-archivo">{selected?.full_name}</DialogTitle>
            <DialogDescription>{selected?.email} · {selected?.phone}{selected?.vehicle_plate ? ` · Plate ${selected.vehicle_plate}` : ''}</DialogDescription>
          </DialogHeader>
          {selected && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge className={VERIF_BADGE[selected.verification_status] || VERIF_BADGE.incomplete}>
                  {selected.verification_status.replace('_', ' ')}
                </Badge>
                {selected.cold_chain_certified && (
                  <Badge className="bg-blue-100 text-blue-700"><Snowflake className="w-3 h-3 mr-1" />Cold chain</Badge>
                )}
                {insuranceFlag(selected)}
              </div>
              {selected.compliance_issues?.length > 0 && (
                <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-xs text-red-700" data-testid="compliance-issues-box">
                  <p className="font-semibold mb-0.5">Not eligible for new jobs:</p>
                  {selected.compliance_issues.map((i) => <p key={i}>· {i}</p>)}
                </div>
              )}

              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Documents</p>
                <div className="grid sm:grid-cols-2 gap-2">
                  {selected.checklist.map((c) => (
                    <div key={c.doc_type} className="flex items-center justify-between bg-slate-50 rounded-lg px-3 py-2" data-testid={`doc-chip-${selected.user_id}-${c.doc_type}`}>
                      <div className="min-w-0 mr-2">
                        <p className="text-xs font-medium text-slate-700 truncate">{c.label}</p>
                        <Badge className={`${DOC_BADGE[c.status]} text-[10px] mt-0.5`}>{c.status}</Badge>
                        {c.insurance_expiry && <p className="text-[10px] text-slate-400 mt-0.5">Expires {c.insurance_expiry}</p>}
                      </div>
                      {c.doc_id && (
                        <div className="flex items-center gap-1 shrink-0">
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => viewDoc(c.doc_id)} title="View document" data-testid={`view-doc-${selected.user_id}-${c.doc_type}`}>
                            <Eye className="w-4 h-4 text-slate-500" />
                          </Button>
                          {c.status === 'pending' && (
                            <>
                              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => reviewDoc(c.doc_id, 'approved')} title="Approve" data-testid={`approve-doc-${selected.user_id}-${c.doc_type}`}>
                                <Check className="w-4 h-4 text-emerald-600" />
                              </Button>
                              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setRejectTarget(c.doc_id)} title="Reject" data-testid={`reject-doc-${selected.user_id}-${c.doc_type}`}>
                                <X className="w-4 h-4 text-red-500" />
                              </Button>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                {selected.verification_status !== 'approved' && (
                  <Button size="sm" className="rounded-full bg-emerald-600 hover:bg-emerald-700" onClick={() => setVerification(selected.user_id, 'approved')} data-testid={`approve-driver-${selected.user_id}-btn`}>
                    <ShieldCheck className="w-4 h-4 mr-1" /> Approve
                  </Button>
                )}
                {selected.verification_status !== 'rejected' && (
                  <Button size="sm" variant="outline" className="rounded-full text-red-600 border-red-200 hover:bg-red-50" onClick={() => setVerification(selected.user_id, 'rejected')} data-testid={`reject-driver-${selected.user_id}-btn`}>
                    <X className="w-4 h-4 mr-1" /> Reject
                  </Button>
                )}
                {selected.verification_status !== 'suspended' && (
                  <Button size="sm" variant="outline" className="rounded-full text-red-700 border-red-300 hover:bg-red-50" onClick={() => setVerification(selected.user_id, 'suspended')} data-testid={`suspend-driver-${selected.user_id}-btn`}>
                    <ShieldOff className="w-4 h-4 mr-1" /> Suspend
                  </Button>
                )}
                {['approved', 'rejected', 'suspended'].includes(selected.verification_status) && (
                  <Button size="sm" variant="outline" className="rounded-full" onClick={() => setVerification(selected.user_id, 'pending_review')} data-testid={`revoke-driver-${selected.user_id}-btn`}>
                    <RotateCcw className="w-4 h-4 mr-1" /> Move back to review
                  </Button>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!rejectTarget} onOpenChange={(o) => { if (!o) { setRejectTarget(null); setRejectNotes(''); } }}>
        <DialogContent data-testid="reject-doc-dialog">
          <DialogHeader>
            <DialogTitle>Reject document</DialogTitle>
            <DialogDescription>The reason is shown to the driver so they can re-submit.</DialogDescription>
          </DialogHeader>
          <Textarea
            placeholder="Reason for rejection (shown to the driver)"
            value={rejectNotes}
            onChange={(e) => setRejectNotes(e.target.value)}
            data-testid="reject-notes-input"
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => { setRejectTarget(null); setRejectNotes(''); }}>Cancel</Button>
            <Button className="bg-red-600 hover:bg-red-700" onClick={confirmReject} data-testid="confirm-reject-doc-btn">Reject</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
