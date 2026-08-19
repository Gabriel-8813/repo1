import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { NotificationBell } from '../components/NotificationBell';
import { useUrgentJobAlerts } from '../hooks/useUrgentJobAlerts';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger
} from '../components/ui/alert-dialog';
import {
  Truck, MapPin, Clock, ArrowDown, LogOut, XCircle, Navigation, Phone,
  Link as LinkIcon, Snowflake, Zap, PenLine, CreditCard, Lock, Package, Building2, EyeOff
} from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const CATEGORY_LABELS = {
  prescription: 'Prescription',
  lab_sample: 'Lab sample',
  biological: 'Biological',
  medical_equipment: 'Medical equipment',
  medical_supply: 'Medical supply',
  other: 'Medical transport'
};

const ACTIVE_STATUS_LABELS = {
  accepted: 'Accepted',
  in_progress: 'In Progress',
  picked_up: 'Picked Up',
  in_transit: 'In Transit'
};

const fullAddress = (addr, city) => {
  if (!addr) return city || '';
  if (city && !addr.toLowerCase().includes(city.toLowerCase())) return `${addr}, ${city}`;
  return addr;
};

const FLAG_META = {
  cold_chain: { icon: Snowflake, label: 'Cold chain', cls: 'bg-sky-100 text-sky-700' },
  urgent: { icon: Zap, label: 'Urgent', cls: 'bg-amber-100 text-amber-700' },
  signature_required: { icon: PenLine, label: 'Signature', cls: 'bg-violet-100 text-violet-700' },
  id_required: { icon: CreditCard, label: 'ID check', cls: 'bg-indigo-100 text-indigo-700' },
  controlled_substance: { icon: Lock, label: 'Controlled', cls: 'bg-rose-100 text-rose-700' },
  fragile: { icon: Package, label: 'Fragile', cls: 'bg-orange-100 text-orange-700' }
};

const JobsPage = () => {
  const navigate = useNavigate();
  const { user, token, logout } = useAuth();
  const [availableJobs, setAvailableJobs] = useState([]);
  const [myJobs, setMyJobs] = useState([]);
  const [fees, setFees] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('available');
  const [nowTick, setNowTick] = useState(Date.now());
  const [busyJobId, setBusyJobId] = useState(null);

  const { newlyArrived } = useUrgentJobAlerts(token, true);

  useEffect(() => {
    fetchJobs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    if (newlyArrived.length > 0) fetchJobs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newlyArrived.length]);

  useEffect(() => {
    const t = setInterval(() => setNowTick(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const fetchJobs = async () => {
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const [availableRes, myJobsRes, feesRes] = await Promise.all([
        axios.get(`${API}/jobs/available`, { headers }),
        axios.get(`${API}/jobs/my`, { headers }),
        axios.get(`${API}/fees/agreement`)
      ]);
      setAvailableJobs(availableRes.data.jobs);
      setMyJobs(myJobsRes.data.jobs);
      setFees(feesRes.data.agreement);
    } catch (error) {
      console.error('Failed to fetch jobs:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAcceptJob = async (jobId) => {
    setBusyJobId(jobId);
    try {
      await axios.post(`${API}/jobs/${jobId}/accept`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success(`Job accepted — full addresses unlocked. Free cancel within ${fees?.cancellation_grace_minutes || 5} min`);
      await fetchJobs();
      setActiveTab('my');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to accept job');
    } finally {
      setBusyJobId(null);
    }
  };

  const handleDeclineJob = async (jobId) => {
    setBusyJobId(jobId);
    try {
      await axios.post(`${API}/jobs/${jobId}/decline`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setAvailableJobs((jobs) => jobs.filter((j) => j.id !== jobId));
      toast.info('Job removed from your queue');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to decline job');
    } finally {
      setBusyJobId(null);
    }
  };

  const handleCancelJob = async (jobId) => {
    try {
      const r = await axios.post(`${API}/jobs/${jobId}/cancel`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (r.data.charged) {
        toast.warning(`Late cancellation — $${r.data.cancellation_fee.toFixed(2)} fee added to your balance`);
      } else {
        toast.success('Job cancelled — no fee (within grace window)');
      }
      fetchJobs();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to cancel job');
    }
  };

  const copyTipLink = async (jobId) => {
    const url = `${window.location.origin}/tip/${jobId}`;
    try {
      await navigator.clipboard.writeText(url);
      toast.success('Tip link copied — share it with your customer!');
    } catch {
      toast.info('Tip link: ' + url, { duration: 10000 });
    }
  };

  const getGraceRemaining = (job) => {
    if (!fees || !job.accepted_at) return null;
    const elapsed = (nowTick - new Date(job.accepted_at).getTime()) / 1000;
    const graceSeconds = fees.cancellation_grace_minutes * 60;
    const remaining = Math.min(graceSeconds - elapsed, graceSeconds);
    return remaining > 0 ? Math.ceil(remaining) : 0;
  };

  const getUrgencyBadge = (urgency) => {
    const styles = {
      standard: { bg: 'bg-slate-100 text-slate-600', label: 'Standard' },
      urgent: { bg: 'bg-amber-100 text-amber-700', label: 'Urgent' },
      emergency: { bg: 'bg-red-100 text-red-700', label: 'Emergency' }
    };
    return styles[urgency] || styles.standard;
  };

  const categoryLabel = (job) => CATEGORY_LABELS[job.item_category] || job.goods_type || 'Medical transport';

  const jobFlags = (job) => {
    const flags = (job.handling_flags || []).filter((f) => f !== 'urgent');
    if (job.temperature_controlled && !flags.includes('cold_chain')) flags.push('cold_chain');
    return flags.filter((f) => FLAG_META[f]);
  };

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  const activeJobs = myJobs.filter(j => ['accepted', 'in_progress', 'picked_up', 'in_transit'].includes(j.status));
  const completedJobs = myJobs.filter(j => j.status === 'completed' || j.status === 'delivered');

  return (
    <div className="min-h-screen bg-slate-50">
      <nav className="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/dashboard" className="flex items-center gap-2">
              <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
                <Truck className="w-6 h-6 text-white" />
              </div>
              <span className="font-archivo font-bold text-xl text-slate-900">MediTrans</span>
            </Link>
            <div className="hidden md:flex items-center gap-1">
              <Link to="/dashboard" className="nav-link">Dashboard</Link>
              <Link to="/jobs" className="nav-link active">Jobs</Link>
              <Link to="/earnings" className="nav-link">Earnings</Link>
              <Link to="/permits" className="nav-link">Permits</Link>
              <Link to="/billing" className="nav-link">Billing</Link>
              {user?.role === 'admin' && <Link to="/admin" className="nav-link text-purple-700">Admin</Link>}
            </div>
          </div>
          <div className="flex items-center gap-1">
            <NotificationBell />
            <Button variant="ghost" size="sm" onClick={handleLogout} data-testid="logout-btn">
              <LogOut className="w-4 h-4 mr-2" /> Logout
            </Button>
          </div>
        </div>
      </nav>

      <main className="max-w-2xl lg:max-w-4xl mx-auto px-4 sm:px-6 py-6 pb-24">
        <div className="mb-6">
          <h1 className="font-archivo font-bold text-2xl sm:text-3xl text-slate-900">Job Board</h1>
          <p className="text-slate-600 mt-1 text-sm">
            Medical transport jobs · platform takes {fees ? (fees.commission_rate * 100).toFixed(0) : 20}% on completed trips
          </p>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="mb-6 w-full sm:w-auto h-12">
            <TabsTrigger value="available" className="flex-1 sm:flex-none h-10 px-6" data-testid="available-jobs-tab">
              Available ({availableJobs.length})
            </TabsTrigger>
            <TabsTrigger value="my" className="flex-1 sm:flex-none h-10 px-6" data-testid="my-jobs-tab">
              My Jobs ({myJobs.length})
            </TabsTrigger>
          </TabsList>

          <TabsContent value="available">
            {availableJobs.length === 0 ? (
              <Card className="border-0 shadow-sm">
                <CardContent className="py-16 text-center">
                  <Truck className="w-16 h-16 mx-auto mb-4 text-slate-300" />
                  <h3 className="text-xl font-semibold text-slate-900 mb-2">No Jobs Available</h3>
                  <p className="text-slate-500 text-sm">New medical transport requests will appear here — jobs that need cold-chain certification only show once you're certified.</p>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-4">
                {availableJobs.map((job) => {
                  const urgency = getUrgencyBadge(job.urgency);
                  const payout = job.payout_amount ?? job.offered_price ?? 0;
                  const distance = job.distance_km ?? job.estimated_distance_km;
                  const commissionPreview = fees ? (payout * fees.commission_rate) : 0;
                  const flags = jobFlags(job);
                  const busy = busyJobId === job.id;
                  return (
                    <Card key={job.id} className="border-0 shadow-[0_2px_10px_rgba(0,0,0,0.08)]" data-testid={`available-job-card-${job.id}`}>
                      <CardContent className="p-4 sm:p-5">
                        <div className="flex items-start justify-between gap-3 mb-3">
                          <div className="flex items-center gap-2 min-w-0">
                            <div className="w-10 h-10 bg-blue-50 rounded-xl flex items-center justify-center shrink-0">
                              <Building2 className="w-5 h-5 text-blue-600" />
                            </div>
                            <div className="min-w-0">
                              <p className="font-archivo font-bold text-slate-900 truncate" data-testid={`job-facility-${job.id}`}>
                                {job.facility_name || job.title || 'Medical facility'}
                              </p>
                              <p className="text-xs text-slate-500" data-testid={`job-category-${job.id}`}>{categoryLabel(job)}</p>
                            </div>
                          </div>
                          <div className="flex flex-col items-end gap-1 shrink-0">
                            {job.status === 'offered' && (
                              job.assigned_driver_id === user?.id
                                ? <Badge className="bg-blue-600 text-white" data-testid={`offered-badge-${job.id}`}>Offered to you</Badge>
                                : <Badge variant="outline" className="text-blue-600 border-blue-300" data-testid={`offered-badge-${job.id}`}>Open offer</Badge>
                            )}
                            <Badge className={urgency.bg}>{urgency.label}</Badge>
                          </div>
                        </div>

                        {flags.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 mb-3" data-testid={`job-flags-${job.id}`}>
                            {flags.map((f) => {
                              const meta = FLAG_META[f];
                              const Icon = meta.icon;
                              return (
                                <span key={f} className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-medium ${meta.cls}`}>
                                  <Icon className="w-3 h-3" /> {meta.label}
                                </span>
                              );
                            })}
                          </div>
                        )}

                        <div className="bg-slate-50 rounded-xl p-3 mb-3">
                          <div className="flex items-start gap-2">
                            <MapPin className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                            <div className="min-w-0">
                              <p className="text-[11px] uppercase tracking-wide text-slate-600 font-semibold">Pickup area</p>
                              <p className="text-sm font-medium text-slate-800" data-testid={`job-pickup-area-${job.id}`}>{job.pickup_area || job.pickup_city}</p>
                            </div>
                          </div>
                          <div className="flex items-center my-1.5 ml-1">
                            <ArrowDown className="w-3.5 h-3.5 text-slate-300" />
                          </div>
                          <div className="flex items-start gap-2">
                            <MapPin className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
                            <div className="min-w-0">
                              <p className="text-[11px] uppercase tracking-wide text-slate-600 font-semibold">Dropoff area</p>
                              <p className="text-sm font-medium text-slate-800" data-testid={`job-dropoff-area-${job.id}`}>{job.dropoff_area || job.delivery_city}</p>
                            </div>
                          </div>
                          <p className="flex items-center gap-1 text-[11px] text-slate-400 mt-2">
                            <EyeOff className="w-3 h-3" /> Full addresses revealed after you accept
                          </p>
                        </div>

                        <div className="flex items-end justify-between mb-4">
                          <div className="text-sm text-slate-500">
                            {distance != null && <span className="font-medium text-slate-700">{distance} km</span>}
                          </div>
                          <div className="text-right">
                            <p className="font-archivo font-black text-3xl text-slate-900" data-testid={`job-payout-${job.id}`}>${Number(payout).toFixed(2)}</p>
                            <p className="text-[11px] text-slate-600">you keep ${(payout - commissionPreview).toFixed(2)} after commission</p>
                          </div>
                        </div>

                        <div className="flex gap-3">
                          <Button
                            variant="outline"
                            className="flex-1 h-14 rounded-full text-slate-600 border-slate-300 active:scale-[0.98]"
                            disabled={busy}
                            onClick={() => handleDeclineJob(job.id)}
                            data-testid={`decline-job-${job.id}-btn`}
                          >
                            Decline
                          </Button>
                          <Button
                            className="flex-[2] h-14 rounded-full bg-blue-600 hover:bg-blue-700 text-base font-semibold active:scale-[0.98]"
                            disabled={busy}
                            onClick={() => handleAcceptJob(job.id)}
                            data-testid={`accept-job-${job.id}-btn`}
                          >
                            {busy ? 'Working…' : 'Accept'}
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </TabsContent>

          <TabsContent value="my">
            {myJobs.length === 0 ? (
              <Card className="border-0 shadow-sm">
                <CardContent className="py-16 text-center">
                  <Clock className="w-16 h-16 mx-auto mb-4 text-slate-300" />
                  <h3 className="text-xl font-semibold text-slate-900 mb-2">No Jobs Yet</h3>
                  <p className="text-slate-500">Accept a job to get started</p>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-8">
                {activeJobs.length > 0 && (
                  <div>
                    <h2 className="font-archivo font-bold text-lg text-slate-900 mb-4">Active</h2>
                    <div className="space-y-4">
                      {activeJobs.map((job) => {
                        const graceLeft = getGraceRemaining(job);
                        const freeCancel = graceLeft > 0;
                        const payout = job.payout_amount ?? job.offered_price ?? 0;
                        return (
                          <Card key={job.id} className="border-2 border-blue-200 bg-blue-50/50" data-testid={`active-job-card-${job.id}`}>
                            <CardContent className="p-4 sm:p-5">
                              <div className="flex items-center gap-2 mb-3 flex-wrap">
                                <h3 className="font-archivo font-bold text-lg text-slate-900">{job.title || categoryLabel(job)}</h3>
                                <Badge className="bg-blue-100 text-blue-700">{ACTIVE_STATUS_LABELS[job.status] || 'Active'}</Badge>
                                {graceLeft !== null && (
                                  <Badge className={freeCancel ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'} data-testid={`grace-badge-${job.id}`}>
                                    {freeCancel
                                      ? `Free cancel: ${Math.floor(graceLeft / 60)}:${String(graceLeft % 60).padStart(2, '0')}`
                                      : `Cancel fee applies ($${fees?.cancellation_fee.toFixed(2)})`
                                    }
                                  </Badge>
                                )}
                              </div>
                              <div className="bg-white rounded-xl p-3 mb-4 space-y-2">
                                <div className="flex items-start gap-2">
                                  <MapPin className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                                  <div>
                                    <p className="text-[11px] uppercase tracking-wide text-slate-600 font-semibold">Pickup</p>
                                    <p className="text-sm font-medium text-slate-800" data-testid={`job-pickup-full-${job.id}`}>
                                      {fullAddress(job.pickup_address, job.pickup_city)}
                                    </p>
                                  </div>
                                </div>
                                <div className="flex items-start gap-2">
                                  <MapPin className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
                                  <div>
                                    <p className="text-[11px] uppercase tracking-wide text-slate-600 font-semibold">Dropoff</p>
                                    <p className="text-sm font-medium text-slate-800" data-testid={`job-dropoff-full-${job.id}`}>
                                      {fullAddress(job.delivery_address, job.delivery_city)}
                                    </p>
                                  </div>
                                </div>
                                {job.recipient_name && (
                                  <div className="flex items-start gap-2">
                                    <Phone className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" />
                                    <div>
                                      <p className="text-[11px] uppercase tracking-wide text-slate-600 font-semibold">Recipient</p>
                                      <p className="text-sm font-medium text-slate-800" data-testid={`job-recipient-${job.id}`}>
                                        {job.recipient_name}{job.recipient_phone ? ` · ${job.recipient_phone}` : ''}
                                      </p>
                                    </div>
                                  </div>
                                )}
                              </div>
                              <div className="flex items-center justify-between gap-3 flex-wrap">
                                <p className="font-archivo font-bold text-2xl text-slate-900">${Number(payout).toFixed(2)}</p>
                                <div className="flex gap-2">
                                  {['accepted', 'in_progress'].includes(job.status) && (
                                  <AlertDialog>
                                    <AlertDialogTrigger asChild>
                                      <Button variant="outline" className="h-11 rounded-full text-red-600 border-red-200 hover:bg-red-50" data-testid={`cancel-job-${job.id}-btn`}>
                                        <XCircle className="w-4 h-4 mr-2" /> Cancel
                                      </Button>
                                    </AlertDialogTrigger>
                                    <AlertDialogContent>
                                      <AlertDialogHeader>
                                        <AlertDialogTitle>Cancel this job?</AlertDialogTitle>
                                        <AlertDialogDescription>
                                          {freeCancel
                                            ? `You're still within the ${fees?.cancellation_grace_minutes}-minute grace window — no fee will be charged.`
                                            : `Grace window has expired. A $${fees?.cancellation_fee.toFixed(2)} late-cancellation fee will be added to your balance.`
                                          }
                                        </AlertDialogDescription>
                                      </AlertDialogHeader>
                                      <AlertDialogFooter>
                                        <AlertDialogCancel>Keep Job</AlertDialogCancel>
                                        <AlertDialogAction onClick={() => handleCancelJob(job.id)} className="bg-red-600 hover:bg-red-700" data-testid={`confirm-cancel-${job.id}-btn`}>
                                          Cancel Job
                                        </AlertDialogAction>
                                      </AlertDialogFooter>
                                    </AlertDialogContent>
                                  </AlertDialog>
                                  )}
                                  <Button
                                    className="h-11 bg-blue-600 hover:bg-blue-700 rounded-full"
                                    onClick={() => navigate(`/delivery/${job.id}`)}
                                    data-testid={`start-delivery-${job.id}-btn`}
                                  >
                                    <Navigation className="w-4 h-4 mr-2" />
                                    {['picked_up', 'in_transit'].includes(job.status) ? 'Continue Delivery' : 'Start Delivery'}
                                  </Button>
                                </div>
                              </div>
                            </CardContent>
                          </Card>
                        );
                      })}
                    </div>
                  </div>
                )}

                {completedJobs.length > 0 && (
                  <div>
                    <h2 className="font-archivo font-bold text-lg text-slate-900 mb-4">Completed</h2>
                    <div className="space-y-4">
                      {completedJobs.map((job) => (
                        <Card key={job.id} className="border-0 shadow-sm bg-slate-50">
                          <CardContent className="p-4 sm:p-5 flex items-center justify-between gap-4 flex-wrap">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-2">
                                <h3 className="font-semibold text-slate-700">{job.title || categoryLabel(job)}</h3>
                                <Badge className="bg-slate-200 text-slate-600">Completed</Badge>
                              </div>
                              <p className="text-sm text-slate-500">{job.pickup_city || job.pickup_area} → {job.delivery_city || job.dropoff_area}</p>
                            </div>
                            <div className="flex items-center gap-3">
                              <p className="font-archivo font-bold text-xl text-slate-600">${Number(job.payout_amount ?? job.offered_price ?? 0).toFixed(2)}</p>
                              <Button
                                variant="outline"
                                size="sm"
                                className="rounded-full border-pink-200 text-pink-600 hover:bg-pink-50"
                                onClick={() => copyTipLink(job.id)}
                                data-testid={`share-tip-link-${job.id}-btn`}
                              >
                                <LinkIcon className="w-4 h-4 mr-2" /> Share Tip Link
                              </Button>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
};

export default JobsPage;
