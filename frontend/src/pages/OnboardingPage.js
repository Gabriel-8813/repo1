import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Truck, LogOut, Upload, Clock, CheckCircle2, FileText, Snowflake, ShieldCheck } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STATUS_BADGE = {
  missing: { label: 'Missing', cls: 'bg-slate-100 text-slate-600' },
  pending: { label: 'Pending review', cls: 'bg-amber-100 text-amber-700' },
  approved: { label: 'Approved', cls: 'bg-emerald-100 text-emerald-700' },
  rejected: { label: 'Rejected', cls: 'bg-red-100 text-red-700' },
};

export default function OnboardingPage() {
  const { token, logout, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [uploadingType, setUploadingType] = useState(null);
  const [expiryDrafts, setExpiryDrafts] = useState({});
  const [plateDraft, setPlateDraft] = useState('');
  const fileInputRef = useRef(null);
  const pendingTypeRef = useRef(null);

  const headers = { Authorization: `Bearer ${token}` };

  const fetchOnboarding = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/driver/onboarding`, { headers });
      setData(res.data);
      if (res.data.verification_status === 'approved') {
        await refreshUser();
        navigate('/dashboard');
      }
    } catch (e) {
      console.error(e);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    if (!token) return;
    fetchOnboarding();
    const iv = setInterval(fetchOnboarding, 15000);
    return () => clearInterval(iv);
  }, [token, fetchOnboarding]);

  const startUpload = (docType, needsExpiry) => {
    if (needsExpiry && !expiryDrafts[docType]) {
      toast.error('Enter the insurance expiry date first');
      return;
    }
    pendingTypeRef.current = docType;
    fileInputRef.current?.click();
  };

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    const docType = pendingTypeRef.current;
    if (!file || !docType) return;
    if (file.size > 10 * 1024 * 1024) {
      toast.error('File too large (max 10 MB)');
      return;
    }
    setUploadingType(docType);
    try {
      const form = new FormData();
      form.append('file', file);
      if (expiryDrafts[docType]) form.append('insurance_expiry', expiryDrafts[docType]);
      if (docType === 'vehicle_registration' && plateDraft) form.append('vehicle_plate', plateDraft);
      await axios.post(`${API}/driver/documents/${docType}`, form, { headers });
      toast.success('Document uploaded — pending review');
      await fetchOnboarding();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed');
    } finally {
      setUploadingType(null);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  if (!data) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  const requiredItems = data.checklist.filter((c) => c.required);
  const uploadedRequired = requiredItems.filter((c) => c.status !== 'missing' && c.status !== 'rejected').length;
  const holding = data.all_required_submitted && data.verification_status !== 'approved';

  return (
    <div className="min-h-screen bg-slate-50" data-testid="onboarding-page">
      <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp,image/heic,application/pdf" className="hidden" onChange={handleFile} data-testid="onboarding-file-input" />
      <header className="bg-white border-b border-slate-200 px-4 sm:px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 bg-blue-600 rounded-lg flex items-center justify-center">
            <Truck className="w-5 h-5 text-white" />
          </div>
          <span className="font-archivo font-bold text-lg text-slate-900">MediTrans</span>
        </div>
        <Button variant="outline" size="sm" onClick={handleLogout} data-testid="onboarding-logout-btn">
          <LogOut className="w-4 h-4 mr-1" /> Sign out
        </Button>
      </header>

      <main className="max-w-2xl mx-auto px-4 sm:px-6 py-8 pb-24">
        <h1 className="font-archivo font-bold text-2xl sm:text-3xl text-slate-900 mb-2">Driver Verification</h1>
        <p className="text-slate-600 text-sm mb-6">
          Upload your credentials below. Our team reviews every document before you can start accepting medical deliveries.
        </p>

        {holding && (
          <Card className="border-0 bg-blue-600 text-white mb-6" data-testid="verification-holding-banner">
            <CardContent className="p-5 flex items-start gap-4">
              <Clock className="w-8 h-8 shrink-0 mt-0.5" />
              <div>
                <h2 className="font-archivo font-bold text-lg mb-1">Verification in progress</h2>
                <p className="text-blue-100 text-sm">
                  All required documents are in. Our compliance team is reviewing them — you'll unlock the jobs board as soon as you're approved. This page refreshes automatically.
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        <div className="flex items-center justify-between mb-4">
          <span className="text-sm font-semibold text-slate-700" data-testid="onboarding-progress">
            {uploadedRequired} of {requiredItems.length} required documents submitted
          </span>
          <Badge className={holding ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600'} data-testid="onboarding-verification-status">
            {data.verification_status.replace('_', ' ')}
          </Badge>
        </div>
        <div className="w-full h-2 bg-slate-200 rounded-full mb-6">
          <div className="h-2 bg-blue-600 rounded-full transition-all" style={{ width: `${(uploadedRequired / requiredItems.length) * 100}%` }}></div>
        </div>

        <div className="space-y-3">
          {data.checklist.map((item) => {
            const badge = STATUS_BADGE[item.status] || STATUS_BADGE.missing;
            const isUploading = uploadingType === item.doc_type;
            return (
              <Card key={item.doc_type} className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]" data-testid={`doc-card-${item.doc_type}`}>
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3 min-w-0">
                      <div className="w-9 h-9 bg-slate-100 rounded-lg flex items-center justify-center shrink-0">
                        {item.doc_type === 'cold_chain_cert'
                          ? <Snowflake className="w-4 h-4 text-blue-500" />
                          : <FileText className="w-4 h-4 text-slate-500" />}
                      </div>
                      <div className="min-w-0">
                        <p className="font-semibold text-slate-900 text-sm">{item.label}</p>
                        {!item.required && (
                          <p className="text-xs text-blue-600 mt-0.5">Optional — unlocks cold-chain jobs</p>
                        )}
                        {item.original_filename && (
                          <p className="text-xs text-slate-400 mt-0.5 truncate">{item.original_filename}</p>
                        )}
                        {item.status === 'rejected' && item.review_notes && (
                          <p className="text-xs text-red-600 mt-1" data-testid={`doc-reject-reason-${item.doc_type}`}>
                            Reason: {item.review_notes}
                          </p>
                        )}
                      </div>
                    </div>
                    <Badge className={`${badge.cls} shrink-0`} data-testid={`doc-status-${item.doc_type}`}>{badge.label}</Badge>
                  </div>

                  {item.doc_type === 'vehicle_registration' && item.status !== 'approved' && (
                    <div className="mt-3">
                      <label className="text-xs text-slate-500 block mb-1">Licence plate number</label>
                      <Input
                        type="text"
                        placeholder="e.g. CVRT 123"
                        value={plateDraft}
                        onChange={(e) => setPlateDraft(e.target.value.toUpperCase())}
                        className="h-9 max-w-[200px]"
                        data-testid="vehicle-plate-input"
                      />
                    </div>
                  )}

                  {item.needs_expiry && item.status !== 'approved' && (
                    <div className="mt-3">
                      <label className="text-xs text-slate-500 block mb-1">Insurance expiry date (min $2M liability)</label>
                      <Input
                        type="date"
                        value={expiryDrafts[item.doc_type] || item.insurance_expiry || ''}
                        onChange={(e) => setExpiryDrafts((d) => ({ ...d, [item.doc_type]: e.target.value }))}
                        className="h-9 max-w-[200px]"
                        data-testid="insurance-expiry-input"
                      />
                    </div>
                  )}

                  {item.status !== 'approved' && (
                    <Button
                      size="sm"
                      variant={item.status === 'missing' || item.status === 'rejected' ? 'default' : 'outline'}
                      className={`mt-3 rounded-full ${item.status === 'missing' || item.status === 'rejected' ? 'bg-blue-600 hover:bg-blue-700' : ''}`}
                      disabled={isUploading}
                      onClick={() => startUpload(item.doc_type, item.needs_expiry)}
                      data-testid={`upload-btn-${item.doc_type}`}
                    >
                      <Upload className="w-4 h-4 mr-1" />
                      {isUploading ? 'Uploading…' : item.status === 'missing' ? 'Upload' : 'Replace'}
                    </Button>
                  )}
                  {item.status === 'approved' && (
                    <div className="mt-3 flex items-center gap-1 text-emerald-600 text-xs font-medium">
                      <CheckCircle2 className="w-4 h-4" /> Verified by our team
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>

        <div className="mt-8 bg-white rounded-xl p-4 border border-slate-200 flex items-start gap-3">
          <ShieldCheck className="w-5 h-5 text-blue-600 shrink-0 mt-0.5" />
          <p className="text-xs text-slate-500">
            Documents are stored securely and only visible to you and the MediTrans compliance team. Accepted formats: JPG, PNG, WEBP, HEIC, PDF (max 10 MB).
          </p>
        </div>
      </main>
    </div>
  );
}
