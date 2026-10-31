import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Truck, ShieldCheck, ShieldAlert, Search, CheckCircle2, Clock, MapPin, HeartHandshake, CloudSnow } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STATUS_LABELS = {
  open: 'Awaiting courier', offered: 'Courier being assigned', accepted: 'Courier assigned',
  picked_up: 'Sealed & picked up', in_transit: 'In transit — sealed', delivered: 'Delivered — seal verified',
  completed: 'Delivered — seal verified', returned: 'Returned to facility', cancelled: 'Cancelled'
};

const fmt = (iso) => iso ? new Date(iso).toLocaleString('en-CA', { dateStyle: 'medium', timeStyle: 'short' }) : null;

export default function VerifySealPage() {
  const { code: urlCode } = useParams();
  const navigate = useNavigate();
  const [code, setCode] = useState(urlCode || '');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const lookup = useCallback(async (c) => {
    if (!c) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const r = await axios.get(`${API}/public/verify/${encodeURIComponent(c.trim())}`);
      setResult(r.data);
    } catch (e) {
      setError(e.response?.status === 404 ? 'No sealed delivery found for this code. Check the code and try again.' : 'Could not verify right now — please try again.');
    } finally { setBusy(false); }
  }, []);

  useEffect(() => { if (urlCode) lookup(urlCode); }, [urlCode, lookup]);

  const submit = (e) => {
    e.preventDefault();
    navigate(`/verify/${encodeURIComponent(code.trim().toUpperCase())}`);
    lookup(code);
  };

  const steps = result ? [
    ['Booked by pharmacy', result.created_at],
    ['Courier assigned', result.accepted_at],
    ['Sealed & picked up', result.picked_up_at],
    ['Delivered', result.delivered_at]
  ] : [];

  const pickupCheck = result?.seal_checks?.find((c) => c.stage === 'pickup');
  const deliveryCheck = result?.seal_checks?.find((c) => c.stage === 'delivery');
  const anyBroken = result?.seal_checks?.some((c) => !c.intact);

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-slate-50 to-emerald-50 px-6 py-10" data-testid="verify-seal-page">
      <div className="max-w-xl mx-auto">
        <Link to="/" className="flex items-center gap-2 mb-8">
          <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
            <Truck className="w-6 h-6 text-white" />
          </div>
          <span className="font-archivo font-bold text-xl text-slate-900">MediTrans</span>
          <Badge variant="outline" className="ml-1 text-emerald-700 border-emerald-200 bg-emerald-50">SealTrace™</Badge>
        </Link>

        <h1 className="font-archivo font-bold text-2xl sm:text-3xl text-slate-900 mb-2">Verify a sealed delivery</h1>
        <p className="text-slate-600 text-sm mb-6">
          Every MediTrans delivery carries a tamper-evident seal code. Enter it below to see the sealed journey — no account needed.
        </p>

        <form onSubmit={submit} className="flex gap-2 mb-8">
          <Input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="e.g. MT-4F7A2C"
            className="h-12 bg-white font-mono tracking-widest uppercase"
            data-testid="seal-code-input"
          />
          <Button type="submit" disabled={busy || !code.trim()} className="h-12 px-6 rounded-full bg-blue-600 hover:bg-blue-700" data-testid="verify-seal-btn">
            <Search className="w-4 h-4 mr-1" /> {busy ? 'Checking…' : 'Verify'}
          </Button>
        </form>

        {error && (
          <Card className="border-0 shadow-sm bg-amber-50 border-amber-200" data-testid="verify-error">
            <CardContent className="p-5 text-sm text-amber-800">{error}</CardContent>
          </Card>
        )}

        {result && (
          <Card className="border-0 shadow-[0_4px_18px_rgba(0,0,0,0.08)]" data-testid="verify-result">
            <CardContent className="p-6">
              <div className="flex items-center justify-between gap-2 mb-1">
                <p className="font-mono font-bold text-lg text-slate-900" data-testid="verify-seal-code">{result.seal_code}</p>
                {anyBroken ? (
                  <Badge className="bg-red-100 text-red-700"><ShieldAlert className="w-3.5 h-3.5 mr-1" /> Seal exception reported</Badge>
                ) : (
                  <Badge className="bg-emerald-100 text-emerald-700"><ShieldCheck className="w-3.5 h-3.5 mr-1" /> Sealed custody</Badge>
                )}
              </div>
              <p className="text-sm text-slate-600 mb-1">{STATUS_LABELS[result.status] || result.status}</p>
              <p className="text-xs text-slate-500 flex items-center gap-1 mb-4">
                <MapPin className="w-3 h-3" />
                {result.facility_name ? `${result.facility_name} · ` : ''}{result.pickup_city || 'Ontario'} → {result.delivery_city || 'Ontario'}
              </p>

              <div className="flex flex-wrap gap-1.5 mb-5">
                {result.care_handoff && <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-medium bg-pink-100 text-pink-700"><HeartHandshake className="w-3 h-3" /> Care handoff</span>}
                {result.storm_priority && <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-medium bg-cyan-100 text-cyan-700"><CloudSnow className="w-3 h-3" /> Storm-ready</span>}
                {result.urgency !== 'standard' && <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-medium bg-amber-100 text-amber-700">{result.urgency}</span>}
              </div>

              <div className="space-y-0" data-testid="verify-timeline">
                {steps.map(([label, ts], i) => (
                  <div key={label} className="flex gap-3">
                    <div className="flex flex-col items-center">
                      <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${ts ? 'bg-emerald-100' : 'bg-slate-100'}`}>
                        {ts ? <CheckCircle2 className="w-4 h-4 text-emerald-600" /> : <Clock className="w-4 h-4 text-slate-400" />}
                      </div>
                      {i < steps.length - 1 && <div className={`w-0.5 flex-1 min-h-[18px] ${ts ? 'bg-emerald-200' : 'bg-slate-200'}`}></div>}
                    </div>
                    <div className="pb-4">
                      <p className={`text-sm font-medium ${ts ? 'text-slate-900' : 'text-slate-400'}`}>{label}</p>
                      {ts && <p className="text-xs text-slate-500">{fmt(ts)}</p>}
                    </div>
                  </div>
                ))}
              </div>

              <div className="border-t border-slate-100 pt-4 mt-1 space-y-2">
                {[['Pickup seal check', pickupCheck], ['Delivery seal check', deliveryCheck]].map(([label, chk]) => (
                  <div key={label} className="flex items-center justify-between text-sm">
                    <span className="text-slate-600">{label}</span>
                    {chk ? (
                      chk.intact
                        ? <span className="inline-flex items-center gap-1 text-emerald-700 font-medium"><ShieldCheck className="w-4 h-4" /> Intact · {fmt(chk.timestamp)}</span>
                        : <span className="inline-flex items-center gap-1 text-red-600 font-medium"><ShieldAlert className="w-4 h-4" /> Exception · {fmt(chk.timestamp)}</span>
                    ) : <span className="text-slate-400">Pending</span>}
                  </div>
                ))}
              </div>

              <p className="text-[11px] text-slate-400 mt-5 border-t border-slate-100 pt-4">
                SealTrace™ shows the sealed journey only — no names, addresses or health details are ever shared on this page. Personal data is encrypted at rest and auto-redacted after the retention period.
              </p>
            </CardContent>
          </Card>
        )}

        {!result && !error && (
          <p className="text-xs text-slate-400 text-center mt-8">
            Pharmacies: your patients receive this code with their delivery confirmation.
          </p>
        )}

        <p className="text-center mt-8">
          <Link to="/" className="text-sm text-blue-600 hover:underline" data-testid="verify-back-home-link">← Back to MediTrans home</Link>
        </p>
      </div>
    </div>
  );
}
