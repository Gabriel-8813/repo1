import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useUrgentJobAlerts } from '../hooks/useUrgentJobAlerts';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger
} from '../components/ui/alert-dialog';
import { 
  Truck, MapPin, Clock, CheckCircle, 
  ArrowRight, Thermometer, LogOut, XCircle, Link as LinkIcon
} from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const JobsPage = () => {
  const navigate = useNavigate();
  const { user, token, logout } = useAuth();
  const [availableJobs, setAvailableJobs] = useState([]);
  const [myJobs, setMyJobs] = useState([]);
  const [fees, setFees] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('available');
  const [nowTick, setNowTick] = useState(Date.now());

  // Live alerts for newly posted urgent/emergency jobs (toasts + auto-refresh)
  const { newlyArrived } = useUrgentJobAlerts(token, true);

  useEffect(() => {
    fetchJobs();
  }, [token]);

  // Auto-refresh list when a new urgent job arrives
  useEffect(() => {
    if (newlyArrived.length > 0) fetchJobs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newlyArrived.length]);

  // Tick every 10s to refresh cancel-grace countdowns
  useEffect(() => {
    const t = setInterval(() => setNowTick(Date.now()), 10000);
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
    try {
      await axios.post(`${API}/jobs/${jobId}/accept`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success('Job accepted — remember, free cancel within ' + (fees?.cancellation_grace_minutes || 5) + ' min');
      fetchJobs();
      setActiveTab('my');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to accept job');
    }
  };

  const handleCompleteJob = async (jobId) => {
    try {
      const r = await axios.post(`${API}/jobs/${jobId}/complete`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const { gross_earnings, commission_charged, net_earnings } = r.data;
      toast.success(`Trip complete! Gross $${gross_earnings?.toFixed(2)} − commission $${commission_charged?.toFixed(2)} = net $${net_earnings?.toFixed(2)}`);
      fetchJobs();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to complete job');
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
      // Fallback: prompt
      toast.info('Tip link: ' + url, { duration: 10000 });
    }
  };

  const getGraceRemaining = (job) => {
    if (!fees || !job.accepted_at) return null;
    const elapsed = (nowTick - new Date(job.accepted_at).getTime()) / 1000;
    const graceSeconds = fees.cancellation_grace_minutes * 60;
    const remaining = graceSeconds - elapsed;
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

  const inProgressJobs = myJobs.filter(j => j.status === 'in_progress');
  const completedJobs = myJobs.filter(j => j.status === 'completed');

  return (
    <div className="min-h-screen bg-slate-50">
      <nav className="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
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
              <Link to="/permits" className="nav-link">Permits</Link>
              <Link to="/billing" className="nav-link">Billing</Link>
              {user?.role === 'admin' && <Link to="/admin" className="nav-link text-purple-700">Admin</Link>}
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={handleLogout} data-testid="logout-btn">
            <LogOut className="w-4 h-4 mr-2" /> Logout
          </Button>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-8">
        <div className="mb-8">
          <h1 className="font-archivo font-bold text-3xl text-slate-900">Job Board</h1>
          <p className="text-slate-600 mt-1">
            Browse medical transport jobs · platform takes {fees ? (fees.commission_rate * 100).toFixed(0) : 20}% on completed trips
          </p>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="mb-6">
            <TabsTrigger value="available" data-testid="available-jobs-tab">
              Available Jobs ({availableJobs.length})
            </TabsTrigger>
            <TabsTrigger value="my" data-testid="my-jobs-tab">
              My Jobs ({myJobs.length})
            </TabsTrigger>
          </TabsList>

          <TabsContent value="available">
            {availableJobs.length === 0 ? (
              <Card className="border-0 shadow-sm">
                <CardContent className="py-16 text-center">
                  <Truck className="w-16 h-16 mx-auto mb-4 text-slate-300" />
                  <h3 className="text-xl font-semibold text-slate-900 mb-2">No Jobs Available</h3>
                  <p className="text-slate-500">Check back soon for new medical transport requests</p>
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-4">
                {availableJobs.map((job) => {
                  const urgency = getUrgencyBadge(job.urgency);
                  const commissionPreview = fees ? (job.offered_price * fees.commission_rate).toFixed(2) : '0';
                  return (
                    <Card key={job.id} className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)] hover:shadow-[0_8px_24px_rgba(0,0,0,0.12)] transition-shadow">
                      <CardContent className="p-6">
                        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-3 flex-wrap">
                              <h3 className="font-archivo font-bold text-xl text-slate-900">{job.title}</h3>
                              <Badge className={urgency.bg}>{urgency.label}</Badge>
                              {job.temperature_controlled && (
                                <Badge variant="outline" className="text-blue-600 border-blue-200">
                                  <Thermometer className="w-3 h-3 mr-1" /> Temp Controlled
                                </Badge>
                              )}
                            </div>
                            <div className="flex flex-wrap items-center gap-4 text-sm text-slate-600 mb-3">
                              <span className="flex items-center gap-1">
                                <MapPin className="w-4 h-4 text-slate-400" />
                                {job.pickup_address}, {job.pickup_city}
                              </span>
                              <ArrowRight className="w-4 h-4 text-slate-400" />
                              <span className="flex items-center gap-1">
                                <MapPin className="w-4 h-4 text-slate-400" />
                                {job.delivery_address}, {job.delivery_city}
                              </span>
                            </div>
                            <div className="flex items-center gap-4 text-sm text-slate-500">
                              <span>Distance: {job.estimated_distance_km} km</span>
                              <span>Type: {job.goods_type}</span>
                            </div>
                            {job.notes && (
                              <p className="mt-3 text-sm text-slate-600 bg-slate-50 p-3 rounded-lg">{job.notes}</p>
                            )}
                          </div>
                          <div className="flex flex-col items-end gap-3 min-w-[180px]">
                            <div className="text-right">
                              <p className="text-sm text-slate-500">Offered Price</p>
                              <p className="font-archivo font-black text-3xl text-slate-900">
                                ${job.offered_price.toFixed(2)}
                              </p>
                              <p className="text-xs text-slate-400">
                                commission ${commissionPreview} · you keep ${(job.offered_price - commissionPreview).toFixed(2)}
                              </p>
                            </div>
                            <Button
                              className="bg-blue-600 hover:bg-blue-700 rounded-full px-8"
                              onClick={() => handleAcceptJob(job.id)}
                              data-testid={`accept-job-${job.id}-btn`}
                            >
                              Accept Job
                            </Button>
                          </div>
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
                {inProgressJobs.length > 0 && (
                  <div>
                    <h2 className="font-archivo font-bold text-lg text-slate-900 mb-4">In Progress</h2>
                    <div className="grid gap-4">
                      {inProgressJobs.map((job) => {
                        const graceLeft = getGraceRemaining(job);
                        const freeCancel = graceLeft > 0;
                        return (
                          <Card key={job.id} className="border-2 border-blue-200 bg-blue-50/50">
                            <CardContent className="p-6">
                              <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                                <div className="flex-1">
                                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                                    <h3 className="font-archivo font-bold text-lg text-slate-900">{job.title}</h3>
                                    <Badge className="bg-blue-100 text-blue-700">In Progress</Badge>
                                    {graceLeft !== null && (
                                      <Badge className={freeCancel ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'} data-testid={`grace-badge-${job.id}`}>
                                        {freeCancel
                                          ? `Free cancel: ${Math.floor(graceLeft / 60)}:${String(graceLeft % 60).padStart(2, '0')}`
                                          : `Cancel fee applies ($${fees?.cancellation_fee.toFixed(2)})`
                                        }
                                      </Badge>
                                    )}
                                  </div>
                                  <p className="text-sm text-slate-600">
                                    {job.pickup_city} → {job.delivery_city} • {job.estimated_distance_km} km
                                  </p>
                                </div>
                                <div className="flex flex-col items-end gap-2">
                                  <p className="font-archivo font-bold text-2xl text-slate-900">
                                    ${job.offered_price.toFixed(2)}
                                  </p>
                                  <div className="flex gap-2">
                                    <AlertDialog>
                                      <AlertDialogTrigger asChild>
                                        <Button variant="outline" className="rounded-full text-red-600 border-red-200 hover:bg-red-50" data-testid={`cancel-job-${job.id}-btn`}>
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
                                    <Button
                                      className="bg-emerald-600 hover:bg-emerald-700 rounded-full"
                                      onClick={() => handleCompleteJob(job.id)}
                                      data-testid={`complete-job-${job.id}-btn`}
                                    >
                                      <CheckCircle className="w-4 h-4 mr-2" /> Complete
                                    </Button>
                                  </div>
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
                    <div className="grid gap-4">
                      {completedJobs.map((job) => (
                        <Card key={job.id} className="border-0 shadow-sm bg-slate-50">
                          <CardContent className="p-6 flex items-center justify-between gap-4 flex-wrap">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-2">
                                <h3 className="font-semibold text-slate-700">{job.title}</h3>
                                <Badge className="bg-slate-200 text-slate-600">Completed</Badge>
                              </div>
                              <p className="text-sm text-slate-500">{job.pickup_city} → {job.delivery_city}</p>
                            </div>
                            <div className="flex items-center gap-3">
                              <p className="font-archivo font-bold text-xl text-slate-600">${job.offered_price.toFixed(2)}</p>
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
