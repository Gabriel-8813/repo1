import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Button } from './ui/button';
import { Card, CardContent } from './ui/card';
import { Badge } from './ui/badge';
import { Textarea } from './ui/textarea';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle
} from './ui/dialog';
import { Eye, Check, X, ShieldCheck, Snowflake } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const VERIF_BADGE = {
  incomplete: 'bg-slate-100 text-slate-600',
  pending_review: 'bg-amber-100 text-amber-700',
  approved: 'bg-emerald-100 text-emerald-700',
  rejected: 'bg-red-100 text-red-700',
};

const DOC_BADGE = {
  missing: 'bg-slate-100 text-slate-500',
  pending: 'bg-amber-100 text-amber-700',
  approved: 'bg-emerald-100 text-emerald-700',
  rejected: 'bg-red-100 text-red-700',
};

export const DriverVerificationTab = () => {
  const { token } = useAuth();
  const [drivers, setDrivers] = useState([]);
  const [rejectTarget, setRejectTarget] = useState(null);
  const [rejectNotes, setRejectNotes] = useState('');

  const headers = { Authorization: `Bearer ${token}` };

  const fetchDrivers = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/driver-verifications`, { headers });
      setDrivers(res.data.drivers);
    } catch (e) {
      toast.error('Failed to load driver verifications');
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

  return (
    <div className="space-y-4" data-testid="driver-verification-tab">
      {drivers.length === 0 && (
        <Card className="border-0 shadow-sm"><CardContent className="p-8 text-center text-slate-500 text-sm">No driver verification records yet.</CardContent></Card>
      )}
      {drivers.map((d) => (
        <Card key={d.user_id} className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]" data-testid={`driver-verification-row-${d.user_id}`}>
          <CardContent className="p-5">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
              <div>
                <p className="font-archivo font-bold text-slate-900">{d.full_name}</p>
                <p className="text-sm text-slate-500">{d.email} · {d.phone}</p>
                {d.insurance_expiry && <p className="text-xs text-slate-400 mt-0.5">Insurance expiry: {d.insurance_expiry}</p>}
              </div>
              <div className="flex items-center gap-2">
                {d.cold_chain_certified && (
                  <Badge className="bg-blue-100 text-blue-700"><Snowflake className="w-3 h-3 mr-1" />Cold chain</Badge>
                )}
                <Badge className={VERIF_BADGE[d.verification_status] || VERIF_BADGE.incomplete} data-testid={`verification-badge-${d.user_id}`}>
                  {d.verification_status.replace('_', ' ')}
                </Badge>
              </div>
            </div>

            <div className="grid sm:grid-cols-2 gap-2 mb-4">
              {d.checklist.map((c) => (
                <div key={c.doc_type} className="flex items-center justify-between bg-slate-50 rounded-lg px-3 py-2" data-testid={`doc-chip-${d.user_id}-${c.doc_type}`}>
                  <div className="min-w-0 mr-2">
                    <p className="text-xs font-medium text-slate-700 truncate">{c.label}</p>
                    <Badge className={`${DOC_BADGE[c.status]} text-[10px] mt-0.5`}>{c.status}</Badge>
                  </div>
                  {c.doc_id && (
                    <div className="flex items-center gap-1 shrink-0">
                      <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => viewDoc(c.doc_id)} title="View document" data-testid={`view-doc-${d.user_id}-${c.doc_type}`}>
                        <Eye className="w-4 h-4 text-slate-500" />
                      </Button>
                      {c.status === 'pending' && (
                        <>
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => reviewDoc(c.doc_id, 'approved')} title="Approve" data-testid={`approve-doc-${d.user_id}-${c.doc_type}`}>
                            <Check className="w-4 h-4 text-emerald-600" />
                          </Button>
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setRejectTarget(c.doc_id)} title="Reject" data-testid={`reject-doc-${d.user_id}-${c.doc_type}`}>
                            <X className="w-4 h-4 text-red-500" />
                          </Button>
                        </>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="flex flex-wrap gap-2">
              {d.verification_status !== 'approved' && (
                <Button size="sm" className="rounded-full bg-emerald-600 hover:bg-emerald-700" onClick={() => setVerification(d.user_id, 'approved')} data-testid={`approve-driver-${d.user_id}-btn`}>
                  <ShieldCheck className="w-4 h-4 mr-1" /> Approve Driver
                </Button>
              )}
              {d.verification_status !== 'rejected' && (
                <Button size="sm" variant="outline" className="rounded-full text-red-600 border-red-200 hover:bg-red-50" onClick={() => setVerification(d.user_id, 'rejected')} data-testid={`reject-driver-${d.user_id}-btn`}>
                  Reject Driver
                </Button>
              )}
              {d.verification_status === 'approved' && (
                <Button size="sm" variant="outline" className="rounded-full" onClick={() => setVerification(d.user_id, 'pending_review')} data-testid={`revoke-driver-${d.user_id}-btn`}>
                  Move back to review
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      ))}

      <Dialog open={!!rejectTarget} onOpenChange={(o) => { if (!o) { setRejectTarget(null); setRejectNotes(''); } }}>
        <DialogContent data-testid="reject-doc-dialog">
          <DialogHeader><DialogTitle>Reject document</DialogTitle></DialogHeader>
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
