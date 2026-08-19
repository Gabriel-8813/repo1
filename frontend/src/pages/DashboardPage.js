import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useUrgentJobAlerts } from '../hooks/useUrgentJobAlerts';
import axios from 'axios';
import { Button } from '../components/ui/button';
import ChangePasswordDialog from '../components/ChangePasswordDialog';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Progress } from '../components/ui/progress';
import { 
  Truck, MapPin, DollarSign, CheckCircle, Clock, 
  AlertTriangle, ArrowRight, FileText, User, LogOut,
  Briefcase, TrendingUp, Shield, Heart
} from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const DashboardPage = () => {
  const navigate = useNavigate();
  const { user, token, logout, refreshUser } = useAuth();
  const [stats, setStats] = useState({ total_earnings: 0, jobs_completed: 0, this_month: 0 });
  const [availableJobs, setAvailableJobs] = useState([]);
  const [myJobs, setMyJobs] = useState([]);
  const [permits, setPermits] = useState({});
  const [requiredPermits, setRequiredPermits] = useState([]);
  const [balance, setBalance] = useState({ owed: 0, paid: 0, entries: [] });
  const [tips, setTips] = useState({ total: 0, count: 0 });
  const [rating, setRating] = useState({ avg: 0, count: 0 });
  const [loading, setLoading] = useState(true);

  // Real-time polling for urgent/emergency jobs — fires toast when new ones appear
  const { urgentCount, newlyArrived, clearNewlyArrived } = useUrgentJobAlerts(token, true);

  useEffect(() => {
    fetchData();
  }, [token]);

  // Refresh dashboard list when a new urgent job is detected
  useEffect(() => {
    if (newlyArrived.length > 0) fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newlyArrived.length]);

  const fetchData = async () => {
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const [statsRes, availableRes, myJobsRes, permitsRes, allPermitsRes, balanceRes, tipsRes, reviewsRes] = await Promise.all([
        axios.get(`${API}/earnings/stats`, { headers }),
        axios.get(`${API}/jobs/available`, { headers }),
        axios.get(`${API}/jobs/my`, { headers }),
        axios.get(`${API}/driver/permits`, { headers }),
        axios.get(`${API}/permits`, { headers }),
        axios.get(`${API}/driver/balance`, { headers }),
        axios.get(`${API}/driver/tips`, { headers }),
        axios.get(`${API}/driver/reviews`, { headers })
      ]);
      
      setStats(statsRes.data);
      setAvailableJobs(availableRes.data.jobs.slice(0, 5));
      setMyJobs(myJobsRes.data.jobs.filter(j => ['accepted', 'in_progress', 'picked_up', 'in_transit'].includes(j.status)).slice(0, 3));
      setPermits(permitsRes.data.permits || {});
      setRequiredPermits(allPermitsRes.data.permits.filter(p => p.required));
      setBalance(balanceRes.data);
      setTips(tipsRes.data);
      setRating(reviewsRes.data.summary);
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAcceptJob = async (jobId) => {
    try {
      await axios.post(`${API}/jobs/${jobId}/accept`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success('Job accepted! Check your active deliveries.');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to accept job');
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const completedPermits = requiredPermits.filter(p => permits[p.id]).length;
  const permitProgress = requiredPermits.length > 0 ? (completedPermits / requiredPermits.length) * 100 : 0;

  const getUrgencyBadge = (urgency) => {
    const styles = {
      standard: 'bg-slate-100 text-slate-600',
      urgent: 'bg-amber-100 text-amber-700',
      emergency: 'bg-red-100 text-red-700'
    };
    return styles[urgency] || styles.standard;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Navigation */}
      <nav className="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6">
              <Link to="/dashboard" className="flex items-center gap-2">
                <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
                  <Truck className="w-6 h-6 text-white" />
                </div>
                <span className="font-archivo font-bold text-xl text-slate-900">MediTrans</span>
              </Link>
              <div className="hidden md:flex items-center gap-1">
                <Link to="/dashboard" className="nav-link active">Dashboard</Link>
                <Link to="/jobs" className="nav-link">Jobs</Link>
                <Link to="/earnings" className="nav-link">Earnings</Link>
                <Link to="/permits" className="nav-link">Permits</Link>
                <Link to="/billing" className="nav-link">Billing</Link>
                {user?.role === 'admin' && (
                  <Link to="/admin" className="nav-link text-purple-700" data-testid="nav-admin-link">Admin</Link>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2 sm:gap-4">
              {user?.role === 'admin' && (
                <Badge className="bg-purple-100 text-purple-700" data-testid="dashboard-admin-badge">Admin</Badge>
              )}
              <ChangePasswordDialog token={token} />
              <Button variant="ghost" size="sm" onClick={handleLogout} data-testid="logout-btn">
                <LogOut className="w-4 h-4 sm:mr-2" /> <span className="hidden sm:inline">Logout</span>
              </Button>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8 overflow-x-hidden">
        {/* Welcome Section */}
        <div className="mb-8">
          <h1 className="font-archivo font-bold text-3xl text-slate-900">
            Welcome back, {user?.full_name?.split(' ')[0]}
          </h1>
          <p className="text-slate-600 mt-1">Here's what's happening with your deliveries.</p>
        </div>

        {/* Live Urgent Jobs Alert */}
        {newlyArrived.length > 0 && (
          <Card className="mb-8 border-red-300 bg-red-50" data-testid="urgent-jobs-alert">
            <CardContent className="p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center mt-0.5">
                    <AlertTriangle className="w-5 h-5 text-red-600" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-slate-900">
                      {newlyArrived.length} new {newlyArrived.length === 1 ? 'urgent job' : 'urgent jobs'} just posted
                    </h3>
                    <ul className="mt-2 space-y-1">
                      {newlyArrived.slice(0, 3).map(j => (
                        <li key={j.id} className="text-sm text-slate-700">
                          <span className={`inline-block w-2 h-2 rounded-full mr-2 ${j.urgency === 'emergency' ? 'bg-red-500' : 'bg-amber-500'}`}></span>
                          <span className="font-medium">{j.title}</span>
                          <span className="text-slate-500"> — {j.pickup_city} → {j.delivery_city} · ${j.offered_price.toFixed(2)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
                <div className="flex gap-2 flex-shrink-0">
                  <Button size="sm" variant="outline" onClick={clearNewlyArrived} data-testid="dismiss-urgent-btn">Dismiss</Button>
                  <Button size="sm" className="bg-red-600 hover:bg-red-700" onClick={() => navigate('/jobs')} data-testid="view-urgent-btn">
                    View All <ArrowRight className="w-3 h-3 ml-1" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Balance Owed Alert */}
        {balance.owed > 0 && (
          <Card className="mb-8 border-amber-200 bg-amber-50" data-testid="dashboard-balance-alert">
            <CardContent className="p-6">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div className="flex items-center gap-4 min-w-0">
                  <div className="w-12 h-12 bg-amber-100 rounded-full flex items-center justify-center shrink-0">
                    <AlertTriangle className="w-6 h-6 text-amber-600" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="font-semibold text-slate-900">Outstanding Balance: ${balance.owed.toFixed(2)} CAD</h3>
                    <p className="text-slate-600 text-sm">Platform commission & cancellation fees pending</p>
                  </div>
                </div>
                <Button onClick={() => navigate('/billing')} className="bg-amber-600 hover:bg-amber-700 shrink-0" data-testid="pay-balance-cta-btn">
                  Pay Balance <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Stats Grid */}
        <div className="grid md:grid-cols-3 xl:grid-cols-6 gap-6 mb-8">
          <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 bg-blue-100 rounded-xl flex items-center justify-center">
                  <DollarSign className="w-6 h-6 text-blue-600" />
                </div>
              </div>
              <p className="text-sm text-slate-500 mb-1">Total Earnings</p>
              <p className="font-archivo font-black text-3xl text-slate-900">
                ${stats.total_earnings.toFixed(2)}
              </p>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 bg-emerald-100 rounded-xl flex items-center justify-center">
                  <CheckCircle className="w-6 h-6 text-emerald-600" />
                </div>
              </div>
              <p className="text-sm text-slate-500 mb-1">Jobs Completed</p>
              <p className="font-archivo font-black text-3xl text-slate-900">
                {stats.jobs_completed}
              </p>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 bg-amber-100 rounded-xl flex items-center justify-center">
                  <TrendingUp className="w-6 h-6 text-amber-600" />
                </div>
              </div>
              <p className="text-sm text-slate-500 mb-1">This Month</p>
              <p className="font-archivo font-black text-3xl text-slate-900">
                ${stats.this_month.toFixed(2)}
              </p>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 bg-pink-100 rounded-xl flex items-center justify-center">
                  <Heart className="w-6 h-6 text-pink-600" />
                </div>
              </div>
              <p className="text-sm text-slate-500 mb-1">Tips Received</p>
              <p className="font-archivo font-black text-3xl text-slate-900" data-testid="dashboard-tips-total">
                ${tips.total.toFixed(2)}
              </p>
              <p className="text-xs text-slate-400 mt-1">{tips.count} tip{tips.count === 1 ? '' : 's'} · 100% yours</p>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]" data-testid="dashboard-rating-card">
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 bg-amber-100 rounded-xl flex items-center justify-center">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6 text-amber-500">
                    <path d="M12 .587l3.668 7.568L24 9.75l-6 5.848L19.335 24 12 20.013 4.665 24 6 15.598 0 9.75l8.332-1.595z"/>
                  </svg>
                </div>
              </div>
              <p className="text-sm text-slate-500 mb-1">Your Rating</p>
              <p className="font-archivo font-black text-3xl text-slate-900" data-testid="dashboard-rating-avg">
                {rating.count === 0 ? '—' : rating.avg.toFixed(1)}
              </p>
              <p className="text-xs text-slate-400 mt-1">
                {rating.count === 0 ? 'No reviews yet' : `${rating.count} review${rating.count === 1 ? '' : 's'}`}
              </p>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 bg-purple-100 rounded-xl flex items-center justify-center">
                  <Shield className="w-6 h-6 text-purple-600" />
                </div>
              </div>
              <p className="text-sm text-slate-500 mb-1">Compliance</p>
              <p className="font-archivo font-black text-3xl text-slate-900">
                {completedPermits}/{requiredPermits.length}
              </p>
              <Progress value={permitProgress} className="mt-2 h-2" />
            </CardContent>
          </Card>
        </div>

        <div className="grid lg:grid-cols-3 gap-8">
          {/* Available Jobs */}
          <div className="lg:col-span-2 min-w-0">
            <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="font-archivo text-xl">Available Jobs</CardTitle>
                <Button variant="ghost" size="sm" onClick={() => navigate('/jobs')} data-testid="view-all-jobs-btn">
                  View All <ArrowRight className="w-4 h-4 ml-1" />
                </Button>
              </CardHeader>
              <CardContent>
                {availableJobs.length === 0 ? (
                  <div className="text-center py-12 text-slate-500">
                    <Briefcase className="w-12 h-12 mx-auto mb-4 text-slate-300" />
                    <p>No jobs available right now</p>
                    <p className="text-sm">Check back soon for new medical transport requests</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {availableJobs.map((job) => (
                      <div key={job.id} className="job-row rounded-lg border border-slate-100 p-3">
                        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-2 flex-wrap">
                              <h3 className="font-semibold text-slate-900 truncate">{job.facility_name || job.title || 'Medical transport'}</h3>
                              <Badge className={getUrgencyBadge(job.urgency)}>
                                {job.urgency}
                              </Badge>
                              {(job.temperature_controlled || (job.handling_flags || []).includes('cold_chain')) && (
                                <Badge variant="outline" className="text-blue-600 border-blue-200">
                                  Cold Chain
                                </Badge>
                              )}
                            </div>
                            <div className="flex items-center gap-3 text-sm text-slate-500 flex-wrap">
                              <span className="flex items-center gap-1 min-w-0">
                                <MapPin className="w-4 h-4 shrink-0" />
                                <span className="truncate">{job.pickup_area || job.pickup_city} → {job.dropoff_area || job.delivery_city}</span>
                              </span>
                              {(job.distance_km ?? job.estimated_distance_km) != null && (
                                <span className="shrink-0">{job.distance_km ?? job.estimated_distance_km} km</span>
                              )}
                            </div>
                          </div>
                          <div className="flex sm:flex-col items-center sm:items-end justify-between gap-2 shrink-0">
                            <p className="font-archivo font-bold text-2xl text-slate-900">
                              ${Number(job.payout_amount ?? job.offered_price ?? 0).toFixed(2)}
                            </p>
                            <Button 
                              size="sm" 
                              className="bg-blue-600 hover:bg-blue-700 rounded-full"
                              onClick={() => handleAcceptJob(job.id)}
                              data-testid={`accept-job-${job.id}-btn`}
                            >
                              Accept Job
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Sidebar */}
          <div className="space-y-6 min-w-0">
            {/* Active Deliveries */}
            <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
              <CardHeader>
                <CardTitle className="font-archivo text-lg">Active Deliveries</CardTitle>
              </CardHeader>
              <CardContent>
                {myJobs.length === 0 ? (
                  <div className="text-center py-8 text-slate-500">
                    <Clock className="w-10 h-10 mx-auto mb-3 text-slate-300" />
                    <p className="text-sm">No active deliveries</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {myJobs.map((job) => (
                      <div key={job.id} className="p-3 bg-blue-50 rounded-lg border border-blue-100" data-testid={`active-delivery-${job.id}`}>
                        <p className="font-medium text-slate-900 text-sm">{job.title || 'Medical transport'}</p>
                        <p className="text-xs text-slate-500 mt-1">
                          {job.pickup_city || job.pickup_area} → {job.delivery_city || job.dropoff_area}
                        </p>
                        <Badge className="mt-2 bg-blue-100 text-blue-700">
                          {{ accepted: 'Accepted', in_progress: 'In Progress', picked_up: 'Picked Up', in_transit: 'In Transit' }[job.status] || 'Active'}
                        </Badge>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Compliance Status */}
            <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="font-archivo text-lg">Compliance</CardTitle>
                <Button variant="ghost" size="sm" onClick={() => navigate('/permits')}>
                  <FileText className="w-4 h-4" />
                </Button>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {requiredPermits.slice(0, 4).map((permit) => (
                    <div key={permit.id} className="flex items-center justify-between">
                      <span className="text-sm text-slate-600 truncate flex-1">{permit.name}</span>
                      {permits[permit.id] ? (
                        <CheckCircle className="w-5 h-5 text-emerald-500 flex-shrink-0" />
                      ) : (
                        <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0" />
                      )}
                    </div>
                  ))}
                </div>
                <Button 
                  variant="outline" 
                  className="w-full mt-4"
                  onClick={() => navigate('/permits')}
                  data-testid="view-permits-btn"
                >
                  View All Requirements
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
};

export default DashboardPage;
