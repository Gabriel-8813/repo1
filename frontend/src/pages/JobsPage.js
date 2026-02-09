import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { 
  Truck, MapPin, DollarSign, Clock, CheckCircle, 
  ArrowRight, Thermometer, AlertTriangle, LogOut
} from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const JobsPage = () => {
  const navigate = useNavigate();
  const { user, token, logout } = useAuth();
  const [availableJobs, setAvailableJobs] = useState([]);
  const [myJobs, setMyJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('available');

  useEffect(() => {
    fetchJobs();
  }, [token]);

  const fetchJobs = async () => {
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const [availableRes, myJobsRes] = await Promise.all([
        axios.get(`${API}/jobs/available`, { headers }),
        axios.get(`${API}/jobs/my`, { headers })
      ]);
      setAvailableJobs(availableRes.data.jobs);
      setMyJobs(myJobsRes.data.jobs);
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
      toast.success('Job accepted successfully!');
      fetchJobs();
      setActiveTab('my');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to accept job');
    }
  };

  const handleCompleteJob = async (jobId) => {
    try {
      await axios.post(`${API}/jobs/${jobId}/complete`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success('Job marked as complete! Payment will be processed.');
      fetchJobs();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to complete job');
    }
  };

  const getUrgencyBadge = (urgency) => {
    const styles = {
      standard: { bg: 'bg-slate-100 text-slate-600', label: 'Standard' },
      urgent: { bg: 'bg-amber-100 text-amber-700', label: 'Urgent' },
      emergency: { bg: 'bg-red-100 text-red-700', label: 'Emergency' }
    };
    return styles[urgency] || styles.standard;
  };

  const getStatusBadge = (status) => {
    const styles = {
      open: { bg: 'bg-emerald-100 text-emerald-700', label: 'Open' },
      in_progress: { bg: 'bg-blue-100 text-blue-700', label: 'In Progress' },
      completed: { bg: 'bg-slate-100 text-slate-600', label: 'Completed' }
    };
    return styles[status] || styles.open;
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
                <Link to="/dashboard" className="nav-link">Dashboard</Link>
                <Link to="/jobs" className="nav-link active">Jobs</Link>
                <Link to="/permits" className="nav-link">Permits</Link>
                <Link to="/billing" className="nav-link">Billing</Link>
              </div>
            </div>
            <Button variant="ghost" size="sm" onClick={handleLogout} data-testid="logout-btn">
              <LogOut className="w-4 h-4 mr-2" /> Logout
            </Button>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-8">
        <div className="mb-8">
          <h1 className="font-archivo font-bold text-3xl text-slate-900">Job Board</h1>
          <p className="text-slate-600 mt-1">Browse and manage medical transport jobs</p>
        </div>

        {/* Subscription Warning */}
        {!user?.subscription_plan && (
          <Card className="mb-8 border-amber-200 bg-amber-50">
            <CardContent className="p-6">
              <div className="flex items-center gap-4">
                <AlertTriangle className="w-8 h-8 text-amber-600" />
                <div className="flex-1">
                  <h3 className="font-semibold text-slate-900">Subscription Required</h3>
                  <p className="text-slate-600 text-sm">You need an active subscription to accept jobs</p>
                </div>
                <Button onClick={() => navigate('/billing')} className="bg-amber-600 hover:bg-amber-700">
                  Subscribe Now
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

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
                  return (
                    <Card key={job.id} className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)] hover:shadow-[0_8px_24px_rgba(0,0,0,0.12)] transition-shadow">
                      <CardContent className="p-6">
                        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-3">
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
                              <p className="mt-3 text-sm text-slate-600 bg-slate-50 p-3 rounded-lg">
                                {job.notes}
                              </p>
                            )}
                          </div>

                          <div className="flex flex-col items-end gap-3">
                            <div className="text-right">
                              <p className="text-sm text-slate-500">Offered Price</p>
                              <p className="font-archivo font-black text-3xl text-slate-900">
                                ${job.offered_price.toFixed(2)}
                              </p>
                              <p className="text-xs text-slate-400">CAD</p>
                            </div>
                            <Button
                              className="bg-blue-600 hover:bg-blue-700 rounded-full px-8"
                              onClick={() => handleAcceptJob(job.id)}
                              disabled={!user?.subscription_plan}
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
                {/* In Progress */}
                {inProgressJobs.length > 0 && (
                  <div>
                    <h2 className="font-archivo font-bold text-lg text-slate-900 mb-4">In Progress</h2>
                    <div className="grid gap-4">
                      {inProgressJobs.map((job) => (
                        <Card key={job.id} className="border-2 border-blue-200 bg-blue-50/50">
                          <CardContent className="p-6">
                            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                              <div className="flex-1">
                                <div className="flex items-center gap-2 mb-2">
                                  <h3 className="font-archivo font-bold text-lg text-slate-900">{job.title}</h3>
                                  <Badge className="bg-blue-100 text-blue-700">In Progress</Badge>
                                </div>
                                <p className="text-sm text-slate-600">
                                  {job.pickup_city} → {job.delivery_city} • {job.estimated_distance_km} km
                                </p>
                              </div>
                              <div className="flex items-center gap-4">
                                <p className="font-archivo font-bold text-2xl text-slate-900">
                                  ${job.offered_price.toFixed(2)}
                                </p>
                                <Button
                                  className="bg-emerald-600 hover:bg-emerald-700 rounded-full"
                                  onClick={() => handleCompleteJob(job.id)}
                                  data-testid={`complete-job-${job.id}-btn`}
                                >
                                  <CheckCircle className="w-4 h-4 mr-2" />
                                  Mark Complete
                                </Button>
                              </div>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  </div>
                )}

                {/* Completed */}
                {completedJobs.length > 0 && (
                  <div>
                    <h2 className="font-archivo font-bold text-lg text-slate-900 mb-4">Completed</h2>
                    <div className="grid gap-4">
                      {completedJobs.map((job) => (
                        <Card key={job.id} className="border-0 shadow-sm bg-slate-50">
                          <CardContent className="p-6">
                            <div className="flex items-center justify-between">
                              <div>
                                <div className="flex items-center gap-2 mb-2">
                                  <h3 className="font-semibold text-slate-700">{job.title}</h3>
                                  <Badge className="bg-slate-200 text-slate-600">Completed</Badge>
                                </div>
                                <p className="text-sm text-slate-500">
                                  {job.pickup_city} → {job.delivery_city}
                                </p>
                              </div>
                              <p className="font-archivo font-bold text-xl text-slate-600">
                                ${job.offered_price.toFixed(2)}
                              </p>
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
