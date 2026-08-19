import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Checkbox } from '../components/ui/checkbox';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger
} from '../components/ui/alert-dialog';
import {
  Truck, MapPin, Navigation, PackageCheck, PenLine, CreditCard,
  CheckCircle2, Undo2, ArrowLeft, Snowflake, ShieldAlert, XCircle, Clock
} from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const getGPS = () => new Promise((resolve) => {
  if (!navigator.geolocation) return resolve({});
  navigator.geolocation.getCurrentPosition(
    (p) => resolve({ gps_lat: p.coords.latitude, gps_lng: p.coords.longitude }),
    () => resolve({}),
    { timeout: 4000, maximumAge: 30000 }
  );
});

const mapsUrl = (addr) => `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(addr || '')}`;

export default function ActiveDeliveryPage() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const { token } = useAuth();
  const headers = { Authorization: `Bearer ${token}` };

  const [job, setJob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [arrived, setArrived] = useState(() => localStorage.getItem(`mt_arrived_${jobId}`) === '1');
  const [returning, setReturning] = useState(false);
  const [settlement, setSettlement] = useState(null);
  const [gpsUnavailable, setGpsUnavailable] = useState(false);
  const [fees, setFees] = useState(null);
  const [nowTick, setNowTick] = useState(Date.now());
  const pingFailsRef = useRef(0);

  // Stage 1 checklist
  const [labelConfirmed, setLabelConfirmed] = useState(false);
  const [countConfirmed, setCountConfirmed] = useState(false);
  const [coolerConfirmed, setCoolerConfirmed] = useState(false);

  // Stage 3 evidence
  const [evidenceMode, setEvidenceMode] = useState('signature');
  const [hasSignature, setHasSignature] = useState(false);
  const [idPhoto, setIdPhoto] = useState(null);
  const [recipientName, setRecipientName] = useState('');
  const [notPatient, setNotPatient] = useState(false);
  const [relationship, setRelationship] = useState('');

  const canvasRef = useRef(null);
  const drawingRef = useRef(false);
  const idInputRef = useRef(null);

  const fetchJob = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/jobs/${jobId}`, { headers });
      setJob(r.data);
      if (r.data.status === 'in_transit' || r.data.status === 'picked_up') {
        const evs = await axios.get(`${API}/jobs/${jobId}/custody-events`, { headers });
        if (evs.data.custody_events.some((e) => e.event_type === 'delivery_attempted')) setReturning(true);
      }
    } catch (e) {
      toast.error('Failed to load job');
      navigate('/jobs');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, token]);

  useEffect(() => { fetchJob(); }, [fetchJob]);

  useEffect(() => {
    axios.get(`${API}/fees/agreement`).then((r) => setFees(r.data.agreement)).catch(() => {});
    const t = setInterval(() => setNowTick(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const graceRemaining = (() => {
    if (!fees || !job?.accepted_at) return null;
    const elapsed = (nowTick - new Date(job.accepted_at).getTime()) / 1000;
    const graceSeconds = fees.cancellation_grace_minutes * 60;
    const remaining = Math.min(graceSeconds - elapsed, graceSeconds);
    return remaining > 0 ? Math.ceil(remaining) : 0;
  })();
  const freeCancel = graceRemaining > 0;

  const cancelJob = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/jobs/${jobId}/cancel`, {}, { headers });
      localStorage.removeItem(`mt_arrived_${jobId}`);
      if (r.data.charged) {
        toast.warning(`Late cancellation — $${r.data.cancellation_fee.toFixed(2)} fee added to your balance`);
      } else {
        toast.success('Job cancelled — no fee (within the free window). It returns to the job pool.');
      }
      navigate('/jobs');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to cancel');
    } finally {
      setBusy(false);
    }
  };

  const isColdChain = job && (job.temperature_controlled || (job.handling_flags || []).includes('cold_chain'));
  const idRequired = job && (job.handling_flags || []).includes('id_required');
  const inTransitStage = job && ['picked_up', 'in_transit'].includes(job.status);

  // Periodic in-transit GPS pings (every 60s while on stage 2)
  useEffect(() => {
    if (!inTransitStage || returning) return;
    let cancelled = false;
    const ping = async () => {
      const gps = await getGPS();
      if (cancelled) return;
      if (gps.gps_lat == null) setGpsUnavailable(true);
      try {
        await axios.post(`${API}/jobs/${jobId}/custody-events`, { event_type: 'in_transit_ping', ...gps }, { headers });
        pingFailsRef.current = 0;
      } catch {
        pingFailsRef.current += 1;
        if (pingFailsRef.current === 2) {
          toast.warning('Trouble logging transit pings — check your connection. Custody trail may have gaps.');
        }
      }
    };
    ping();
    const iv = setInterval(ping, 60000);
    return () => { cancelled = true; clearInterval(iv); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inTransitStage, returning, jobId]);

  const postEvent = async (payload) => {
    const gps = await getGPS();
    if (gps.gps_lat == null) setGpsUnavailable(true);
    const r = await axios.post(`${API}/jobs/${jobId}/custody-events`, { ...payload, ...gps }, { headers });
    return r.data;
  };

  const confirmPickup = async () => {
    setBusy(true);
    try {
      await postEvent({
        event_type: 'pickup_confirmed',
        checklist: { label_confirmed: labelConfirmed, item_count_confirmed: countConfirmed, cooler_confirmed: coolerConfirmed }
      });
      toast.success('Pickup confirmed — custody recorded');
      await fetchJob();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to confirm pickup');
    } finally {
      setBusy(false);
    }
  };

  // Signature pad
  const startDraw = (e) => {
    drawingRef.current = true;
    const c = canvasRef.current; const ctx = c.getContext('2d');
    const rect = c.getBoundingClientRect();
    const pt = e.touches ? e.touches[0] : e;
    ctx.beginPath();
    ctx.moveTo((pt.clientX - rect.left) * (c.width / rect.width), (pt.clientY - rect.top) * (c.height / rect.height));
  };
  const moveDraw = (e) => {
    if (!drawingRef.current) return;
    e.preventDefault();
    const c = canvasRef.current; const ctx = c.getContext('2d');
    const rect = c.getBoundingClientRect();
    const pt = e.touches ? e.touches[0] : e;
    ctx.lineWidth = 2.5; ctx.lineCap = 'round'; ctx.strokeStyle = '#0f172a';
    ctx.lineTo((pt.clientX - rect.left) * (c.width / rect.width), (pt.clientY - rect.top) * (c.height / rect.height));
    ctx.stroke();
    setHasSignature(true);
  };
  const endDraw = () => { drawingRef.current = false; };
  const clearSignature = () => {
    const c = canvasRef.current;
    if (c) c.getContext('2d').clearRect(0, 0, c.width, c.height);
    setHasSignature(false);
  };

  const uploadEvidence = async () => {
    const form = new FormData();
    if (evidenceMode === 'signature') {
      const blob = await new Promise((res) => canvasRef.current.toBlob(res, 'image/png'));
      form.append('file', blob, 'signature.png');
      form.append('kind', 'signature');
    } else {
      form.append('file', idPhoto);
      form.append('kind', 'id_photo');
    }
    const r = await axios.post(`${API}/jobs/${jobId}/delivery-evidence`, form, { headers });
    return r.data.evidence_url;
  };

  const evidenceReady = evidenceMode === 'signature' ? hasSignature : !!idPhoto;
  const canDeliver = evidenceReady && recipientName.trim() && (!notPatient || relationship.trim());

  const markDelivered = async () => {
    setBusy(true);
    try {
      const evidenceUrl = await uploadEvidence();
      const r = await postEvent({
        event_type: 'delivered',
        evidence_url: evidenceUrl,
        recipient_name: recipientName.trim(),
        recipient_relationship: notPatient ? relationship.trim() : null
      });
      setSettlement(r.settlement);
      localStorage.removeItem(`mt_arrived_${jobId}`);
      toast.success('Delivered — chain of custody complete');
      await fetchJob();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to mark delivered');
    } finally {
      setBusy(false);
    }
  };

  const customerUnavailable = async () => {
    setBusy(true);
    try {
      await postEvent({ event_type: 'delivery_attempted', notes: 'Customer unavailable at dropoff' });
      setReturning(true);
      toast.warning('Delivery attempt logged — return the item to the pickup facility. Never leave items unattended.');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to log attempt');
    } finally {
      setBusy(false);
    }
  };

  const confirmReturn = async () => {
    setBusy(true);
    try {
      await postEvent({ event_type: 'returned', notes: 'Item returned to pickup facility' });
      localStorage.removeItem(`mt_arrived_${jobId}`);
      toast.success('Return recorded — facility and dispatch notified');
      await fetchJob();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to record return');
    } finally {
      setBusy(false);
    }
  };

  if (!job) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  const stage = ['delivered', 'completed'].includes(job.status) ? 4
    : job.status === 'returned' ? 5
    : returning ? 3.5
    : inTransitStage ? (arrived ? 3 : 2)
    : 1;

  const stageLabel = { 1: 'Stage 1 · Pickup', 2: 'Stage 2 · In Transit', 3: 'Stage 3 · Delivery', 3.5: 'Return to Facility', 4: 'Delivered', 5: 'Returned' }[stage];

  return (
    <div className="min-h-screen bg-slate-50 pb-24" data-testid="active-delivery-page">
      <header className="bg-white border-b border-slate-200 px-4 py-3 flex items-center justify-between sticky top-0 z-40">
        <Link to="/jobs" className="flex items-center gap-2 text-slate-600 text-sm" data-testid="back-to-jobs-link">
          <ArrowLeft className="w-4 h-4" /> Jobs
        </Link>
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
            <Truck className="w-4 h-4 text-white" />
          </div>
          <span className="font-archivo font-bold text-slate-900">Active Delivery</span>
        </div>
        <Badge className="bg-blue-100 text-blue-700" data-testid="delivery-stage-badge">{stageLabel}</Badge>
      </header>

      <main className="max-w-lg mx-auto px-4 py-6 space-y-4">
        {/* Progress dots */}
        <div className="flex items-center gap-2 justify-center mb-2">
          {[1, 2, 3].map((s) => (
            <div key={s} className={`h-2 rounded-full transition-all ${stage >= s ? 'w-10 bg-blue-600' : 'w-6 bg-slate-200'}`}></div>
          ))}
        </div>

        {isColdChain && stage <= 3 && (
          <div className="flex items-center gap-2 bg-sky-50 border border-sky-200 rounded-xl px-3 py-2 text-sky-700 text-sm">
            <Snowflake className="w-4 h-4 shrink-0" /> Cold-chain shipment — keep insulated at all times
          </div>
        )}

        {gpsUnavailable && stage <= 3.5 && (
          <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2 text-amber-700 text-xs" data-testid="gps-unavailable-warning">
            <ShieldAlert className="w-4 h-4 shrink-0" /> Location unavailable — custody events are recording without GPS. Enable location for a complete trail.
          </div>
        )}

        {/* STAGE 1: PICKUP */}
        {stage === 1 && (
          <>
          {graceRemaining !== null && (
            <div
              className={`flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium border ${freeCancel ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-red-50 border-red-200 text-red-700'}`}
              data-testid="cancel-window-banner"
            >
              <Clock className="w-4 h-4 shrink-0" />
              {freeCancel
                ? `Free cancellation for ${Math.floor(graceRemaining / 60)}:${String(graceRemaining % 60).padStart(2, '0')} — after that a $${fees?.cancellation_fee.toFixed(2)} fee applies`
                : `Free-cancel window over — cancelling now costs $${fees?.cancellation_fee.toFixed(2)}`}
            </div>
          )}
          <Card className="border-0 shadow-[0_2px_10px_rgba(0,0,0,0.08)]" data-testid="pickup-stage">
            <CardContent className="p-5">
              <h2 className="font-archivo font-bold text-xl text-slate-900 mb-3">Pick up at facility</h2>
              <div className="bg-slate-50 rounded-xl p-3 mb-3">
                <div className="flex items-start gap-2">
                  <MapPin className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                  <p className="text-sm font-medium text-slate-800" data-testid="pickup-full-address">
                    {job.pickup_address}{job.pickup_city && !job.pickup_address?.toLowerCase().includes(job.pickup_city.toLowerCase()) ? `, ${job.pickup_city}` : ''}
                  </p>
                </div>
              </div>
              <a href={mapsUrl(job.pickup_address)} target="_blank" rel="noreferrer">
                <Button variant="outline" className="w-full h-12 rounded-full mb-5" data-testid="navigate-pickup-btn">
                  <Navigation className="w-4 h-4 mr-2" /> Navigate to pickup
                </Button>
              </a>

              <h3 className="font-semibold text-slate-900 text-sm mb-3">Pickup checklist (required)</h3>
              <div className="space-y-3">
                <label className="flex items-start gap-3 p-3 bg-slate-50 rounded-xl cursor-pointer">
                  <Checkbox checked={labelConfirmed} onCheckedChange={(v) => setLabelConfirmed(!!v)} className="mt-0.5" data-testid="checklist-label" />
                  <span className="text-sm text-slate-700">Recipient name on the label matches this job</span>
                </label>
                <label className="flex items-start gap-3 p-3 bg-slate-50 rounded-xl cursor-pointer">
                  <Checkbox checked={countConfirmed} onCheckedChange={(v) => setCountConfirmed(!!v)} className="mt-0.5" data-testid="checklist-count" />
                  <span className="text-sm text-slate-700">Item count confirmed with facility staff</span>
                </label>
                {isColdChain && (
                  <label className="flex items-start gap-3 p-3 bg-sky-50 border border-sky-200 rounded-xl cursor-pointer">
                    <Checkbox checked={coolerConfirmed} onCheckedChange={(v) => setCoolerConfirmed(!!v)} className="mt-0.5" data-testid="checklist-cooler" />
                    <span className="text-sm text-sky-800 font-medium">Insulated cooler in use (required for cold chain)</span>
                  </label>
                )}
              </div>

              <Button
                className="w-full h-14 rounded-full bg-blue-600 hover:bg-blue-700 text-base font-semibold mt-5"
                disabled={busy || !labelConfirmed || !countConfirmed || (isColdChain && !coolerConfirmed)}
                onClick={confirmPickup}
                data-testid="confirm-pickup-btn"
              >
                <PackageCheck className="w-5 h-5 mr-2" /> {busy ? 'Recording…' : 'Confirm Pickup'}
              </Button>

              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="outline" className="w-full h-12 rounded-full mt-3 text-red-600 border-red-200 hover:bg-red-50" data-testid="cancel-delivery-btn">
                    <XCircle className="w-4 h-4 mr-2" /> Cancel this job {freeCancel ? '(free)' : `($${fees?.cancellation_fee?.toFixed(2)} fee)`}
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Cancel this job?</AlertDialogTitle>
                    <AlertDialogDescription>
                      {freeCancel
                        ? `You're within the ${fees?.cancellation_grace_minutes}-minute free window — no fee. The job returns to the pool for other drivers.`
                        : `The free-cancel window has expired. A $${fees?.cancellation_fee?.toFixed(2)} late-cancellation fee will be added to your balance and logged.`}
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Keep Job</AlertDialogCancel>
                    <AlertDialogAction onClick={cancelJob} className="bg-red-600 hover:bg-red-700" data-testid="confirm-cancel-delivery-btn">
                      Cancel Job
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </CardContent>
          </Card>
          </>
        )}

        {/* STAGE 2: IN TRANSIT */}
        {stage === 2 && (
          <Card className="border-0 shadow-[0_2px_10px_rgba(0,0,0,0.08)]" data-testid="transit-stage">
            <CardContent className="p-5">
              <h2 className="font-archivo font-bold text-xl text-slate-900 mb-1">In transit</h2>
              <p className="text-xs text-slate-500 mb-3">GPS pings are being recorded to the custody trail automatically.</p>
              <div className="bg-slate-50 rounded-xl p-3 mb-3">
                <div className="flex items-start gap-2">
                  <MapPin className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
                  <p className="text-sm font-medium text-slate-800" data-testid="dropoff-full-address">
                    {job.delivery_address}{job.delivery_city && !job.delivery_address?.toLowerCase().includes(job.delivery_city.toLowerCase()) ? `, ${job.delivery_city}` : ''}
                  </p>
                </div>
              </div>
              <a href={mapsUrl(job.delivery_address)} target="_blank" rel="noreferrer">
                <Button variant="outline" className="w-full h-12 rounded-full mb-4" data-testid="navigate-dropoff-btn">
                  <Navigation className="w-4 h-4 mr-2" /> Navigate to dropoff
                </Button>
              </a>
              <Button className="w-full h-14 rounded-full bg-blue-600 hover:bg-blue-700 text-base font-semibold" onClick={() => { setArrived(true); localStorage.setItem(`mt_arrived_${jobId}`, '1'); }} data-testid="arrived-btn">
                Arrived at dropoff
              </Button>
            </CardContent>
          </Card>
        )}

        {/* STAGE 3: DELIVERY */}
        {stage === 3 && (
          <Card className="border-0 shadow-[0_2px_10px_rgba(0,0,0,0.08)]" data-testid="delivery-stage">
            <CardContent className="p-5">
              <h2 className="font-archivo font-bold text-xl text-slate-900 mb-1">Compliant handoff</h2>
              <p className="text-xs text-slate-500 mb-4">Items can never be left at the door. Capture proof of handoff to a person.</p>

              <div className="flex gap-2 mb-4">
                <Button
                  variant={evidenceMode === 'signature' ? 'default' : 'outline'}
                  className={`flex-1 h-11 rounded-full ${evidenceMode === 'signature' ? 'bg-blue-600 hover:bg-blue-700' : ''}`}
                  onClick={() => setEvidenceMode('signature')}
                  data-testid="evidence-mode-signature"
                >
                  <PenLine className="w-4 h-4 mr-1" /> Signature
                </Button>
                <Button
                  variant={evidenceMode === 'id_photo' ? 'default' : 'outline'}
                  className={`flex-1 h-11 rounded-full ${evidenceMode === 'id_photo' ? 'bg-blue-600 hover:bg-blue-700' : ''}`}
                  onClick={() => setEvidenceMode('id_photo')}
                  data-testid="evidence-mode-id"
                >
                  <CreditCard className="w-4 h-4 mr-1" /> {idRequired ? 'Gov. ID (required option)' : 'Gov. ID photo'}
                </Button>
              </div>

              {evidenceMode === 'signature' ? (
                <div className="mb-4">
                  <p className="text-xs text-slate-500 mb-1">Recipient signs below</p>
                  <canvas
                    ref={canvasRef}
                    width={640}
                    height={240}
                    className="w-full h-40 bg-white border-2 border-dashed border-slate-300 rounded-xl touch-none"
                    onMouseDown={startDraw} onMouseMove={moveDraw} onMouseUp={endDraw} onMouseLeave={endDraw}
                    onTouchStart={startDraw} onTouchMove={moveDraw} onTouchEnd={endDraw}
                    data-testid="signature-canvas"
                  ></canvas>
                  <Button variant="ghost" size="sm" className="mt-1 text-slate-500" onClick={clearSignature} data-testid="clear-signature-btn">Clear</Button>
                </div>
              ) : (
                <div className="mb-4">
                  <input ref={idInputRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => setIdPhoto(e.target.files?.[0] || null)} data-testid="id-photo-input" />
                  <Button variant="outline" className="w-full h-12 rounded-full" onClick={() => idInputRef.current?.click()} data-testid="capture-id-btn">
                    <CreditCard className="w-4 h-4 mr-2" /> {idPhoto ? `Captured: ${idPhoto.name}` : 'Photograph government ID'}
                  </Button>
                </div>
              )}

              <Input
                placeholder="Recipient full name"
                aria-label="Recipient full name"
                value={recipientName}
                onChange={(e) => setRecipientName(e.target.value)}
                className="h-12 mb-3"
                data-testid="recipient-name-input"
              />
              <label className="flex items-center gap-2 mb-3 cursor-pointer">
                <Checkbox checked={notPatient} onCheckedChange={(v) => setNotPatient(!!v)} data-testid="not-patient-checkbox" />
                <span className="text-sm text-slate-600">Signed by someone other than the patient</span>
              </label>
              {notPatient && (
                <Input
                  placeholder="Relationship to patient (e.g. spouse, caregiver)"
                  aria-label="Relationship to patient"
                  value={relationship}
                  onChange={(e) => setRelationship(e.target.value)}
                  className="h-12 mb-3"
                  data-testid="recipient-relationship-input"
                />
              )}

              <Button
                className="w-full h-14 rounded-full bg-emerald-600 hover:bg-emerald-700 text-base font-semibold"
                disabled={busy || !canDeliver}
                onClick={markDelivered}
                data-testid="mark-delivered-btn"
              >
                <CheckCircle2 className="w-5 h-5 mr-2" /> {busy ? 'Recording…' : 'Mark Delivered'}
              </Button>

              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="outline" className="w-full h-12 rounded-full mt-3 text-amber-700 border-amber-300 hover:bg-amber-50" data-testid="customer-unavailable-btn">
                    <ShieldAlert className="w-4 h-4 mr-2" /> Customer Unavailable
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Abort delivery?</AlertDialogTitle>
                    <AlertDialogDescription>
                      The item must be returned to the pickup facility — it can never be left unattended. The facility and dispatch will be notified.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Keep trying</AlertDialogCancel>
                    <AlertDialogAction onClick={customerUnavailable} className="bg-amber-600 hover:bg-amber-700" data-testid="confirm-unavailable-btn">
                      Log attempt & return item
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </CardContent>
          </Card>
        )}

        {/* RETURN PATH */}
        {stage === 3.5 && (
          <Card className="border-2 border-amber-300 bg-amber-50/60" data-testid="return-stage">
            <CardContent className="p-5">
              <h2 className="font-archivo font-bold text-xl text-slate-900 mb-1">Return to pickup facility</h2>
              <p className="text-sm text-slate-600 mb-3">Delivery attempt logged. Bring the item back — it is never abandoned.</p>
              <div className="bg-white rounded-xl p-3 mb-3">
                <div className="flex items-start gap-2">
                  <MapPin className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                  <p className="text-sm font-medium text-slate-800">{job.pickup_address}</p>
                </div>
              </div>
              <a href={mapsUrl(job.pickup_address)} target="_blank" rel="noreferrer">
                <Button variant="outline" className="w-full h-12 rounded-full mb-4 bg-white" data-testid="navigate-return-btn">
                  <Navigation className="w-4 h-4 mr-2" /> Navigate back to facility
                </Button>
              </a>
              <Button className="w-full h-14 rounded-full bg-amber-600 hover:bg-amber-700 text-base font-semibold" disabled={busy} onClick={confirmReturn} data-testid="confirm-return-btn">
                <Undo2 className="w-5 h-5 mr-2" /> {busy ? 'Recording…' : 'Confirm Return to Facility'}
              </Button>
            </CardContent>
          </Card>
        )}

        {/* DONE STATES */}
        {stage === 4 && (
          <Card className="border-0 shadow-[0_2px_10px_rgba(0,0,0,0.08)]" data-testid="delivered-summary">
            <CardContent className="p-6 text-center">
              <div className="w-16 h-16 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <CheckCircle2 className="w-8 h-8 text-emerald-600" />
              </div>
              <h2 className="font-archivo font-bold text-2xl text-slate-900 mb-2">Delivered</h2>
              <p className="text-sm text-slate-500 mb-4">Chain of custody complete with signature/ID evidence.</p>
              {settlement && (
                <div className="bg-slate-50 rounded-xl p-4 text-sm text-slate-700 mb-4">
                  Gross ${settlement.gross_earnings?.toFixed(2)} − commission ${settlement.commission_charged?.toFixed(2)} = <span className="font-bold">net ${settlement.net_earnings?.toFixed(2)}</span>
                </div>
              )}
              <Button className="w-full h-12 rounded-full bg-blue-600 hover:bg-blue-700" onClick={() => navigate('/jobs')} data-testid="back-to-board-btn">
                Back to Job Board
              </Button>
            </CardContent>
          </Card>
        )}

        {stage === 5 && (
          <Card className="border-0 shadow-[0_2px_10px_rgba(0,0,0,0.08)]" data-testid="returned-summary">
            <CardContent className="p-6 text-center">
              <div className="w-16 h-16 bg-amber-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <Undo2 className="w-8 h-8 text-amber-600" />
              </div>
              <h2 className="font-archivo font-bold text-2xl text-slate-900 mb-2">Item Returned</h2>
              <p className="text-sm text-slate-500 mb-4">The facility and dispatcher were notified. Custody trail closed as returned.</p>
              <Button className="w-full h-12 rounded-full bg-blue-600 hover:bg-blue-700" onClick={() => navigate('/jobs')} data-testid="back-to-board-btn">
                Back to Job Board
              </Button>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}
