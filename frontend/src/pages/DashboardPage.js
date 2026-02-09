import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Progress } from '../components/ui/progress';
import { 
  Truck, MapPin, DollarSign, CheckCircle, Clock, 
  AlertTriangle, ArrowRight, FileText, User, LogOut,
  Briefcase, TrendingUp, Shield
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
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, [token]);

  const fetchData = async () => {
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const [statsRes, availableRes, myJobsRes, permitsRes, allPermitsRes] = await Promise.all([
        axios.get(`${API}/earnings/stats`, { headers }),
        axios.get(`${API}/jobs/available`, { headers }),
        axios.get(`${API}/jobs/my`, { headers }),
        axios.get(`${API}/driver/permits`, { headers }),
        axios.get(`${API}/permits`, { headers })
      ]);
      
      setStats(statsRes.data);
      setAvailableJobs(availableRes.data.jobs.slice(0, 5));
      setMyJobs(myJobsRes.data.jobs.filter(j => j.status === 'in_progress').slice(0, 3));
      setPermits(permitsRes.data.permits || {});
      setRequiredPermits(allPermitsRes.data.permits.filter(p => p.required));
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
                <Link to="/permits" className="nav-link">Permits</Link>
                <Link to="/billing" className="nav-link">Billing</Link>
              </div>
            </div>
            <div className="flex items-center gap-4">
              {user?.subscription_plan ? (
                <Badge className="bg-emerald-100 text-emerald-700 capitalize">
                  {user.subscription_plan} Plan
                </Badge>
              ) : (
                <Badge variant="outline" className="text-amber-600 border-amber-300">
                  No Subscription
                </Badge>
              )}
              <Button variant="ghost" size="sm" onClick={handleLogout} data-testid="logout-btn">
                <LogOut className="w-4 h-4 mr-2" /> Logout
              </Button>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Welcome Section */}
        <div className="mb-8">
          <h1 className="font-archivo font-bold text-3xl text-slate-900">
            Welcome back, {user?.full_name?.split(' ')[0]}
          </h1>
          <p className="text-slate-600 mt-1">Here's what's happening with your deliveries.</p>
        </div>

        {/* Subscription Alert */}
        {!user?.subscription_plan && (
          <Card className="mb-8 border-amber-200 bg-amber-50">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 bg-amber-100 rounded-full flex items-center justify-center">
                    <AlertTriangle className="w-6 h-6 text-amber-600" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-slate-900">Subscription Required</h3>
                    <p className="text-slate-600 text-sm">Subscribe to a plan to start accepting jobs</p>
                  </div>
                </div>
                <Button onClick={() => navigate('/billing')} className="bg-amber-600 hover:bg-amber-700" data-testid="subscribe-cta-btn">
                  Subscribe Now <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Stats Grid */}
        <div className="grid md:grid-cols-4 gap-6 mb-8">
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
          <div className="lg:col-span-2">
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
                      <div key={job.id} className="job-row rounded-lg border border-slate-100">
                        <div className="flex items-center justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-2">
                              <h3 className="font-semibold text-slate-900">{job.title}</h3>
                              <Badge className={getUrgencyBadge(job.urgency)}>
                                {job.urgency}
                              </Badge>
                              {job.temperature_controlled && (
                                <Badge variant="outline" className="text-blue-600 border-blue-200">
                                  Temp Controlled
                                </Badge>
                              )}
                            </div>
                            <div className="flex items-center gap-4 text-sm text-slate-500">
                              <span className="flex items-center gap-1">
                                <MapPin className="w-4 h-4" />
                                {job.pickup_city} → {job.delivery_city}
                              </span>
                              <span>{job.estimated_distance_km} km</span>
                            </div>
                          </div>
                          <div className="text-right ml-4">
                            <p className="font-archivo font-bold text-2xl text-slate-900">
                              ${job.offered_price.toFixed(2)}
                            </p>
                            <Button 
                              size="sm" 
                              className="mt-2 bg-blue-600 hover:bg-blue-700 rounded-full"
                              onClick={() => handleAcceptJob(job.id)}
                              disabled={!user?.subscription_plan}
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
          <div className="space-y-6">
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
                      <div key={job.id} className="p-3 bg-blue-50 rounded-lg border border-blue-100">
                        <p className="font-medium text-slate-900 text-sm">{job.title}</p>
                        <p className="text-xs text-slate-500 mt-1">
                          {job.pickup_city} → {job.delivery_city}
                        </p>
                        <Badge className="mt-2 bg-blue-100 text-blue-700">In Progress</Badge>
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
