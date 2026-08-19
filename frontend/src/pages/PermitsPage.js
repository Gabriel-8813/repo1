import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Progress } from '../components/ui/progress';
import { Checkbox } from '../components/ui/checkbox';
import { 
  Truck, Shield, FileText, ExternalLink, CheckCircle, 
  AlertTriangle, Info, LogOut
} from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const PermitsPage = () => {
  const navigate = useNavigate();
  const { user, token, logout } = useAuth();
  const [permits, setPermits] = useState([]);
  const [driverPermits, setDriverPermits] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPermits();
  }, [token]);

  const fetchPermits = async () => {
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const [allPermitsRes, driverPermitsRes] = await Promise.all([
        axios.get(`${API}/permits`, { headers }),
        axios.get(`${API}/driver/permits`, { headers })
      ]);
      setPermits(allPermitsRes.data.permits);
      setDriverPermits(driverPermitsRes.data.permits || {});
    } catch (error) {
      console.error('Failed to fetch permits:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleTogglePermit = async (permitId, completed) => {
    try {
      await axios.put(
        `${API}/driver/permits/${permitId}?completed=${completed}`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setDriverPermits(prev => ({ ...prev, [permitId]: completed }));
      toast.success(completed ? 'Permit marked as obtained' : 'Permit marked as pending');
    } catch (error) {
      toast.error('Failed to update permit status');
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const requiredPermits = permits.filter(p => p.required);
  const optionalPermits = permits.filter(p => !p.required);
  const completedCount = requiredPermits.filter(p => driverPermits[p.id]).length;
  const progress = requiredPermits.length > 0 ? (completedCount / requiredPermits.length) * 100 : 0;

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
                <Link to="/dashboard" className="nav-link">Dashboard</Link>
                <Link to="/jobs" className="nav-link">Jobs</Link>
                <Link to="/earnings" className="nav-link">Earnings</Link>
                <Link to="/permits" className="nav-link active">Permits</Link>
                <Link to="/billing" className="nav-link">Billing</Link>
              </div>
            </div>
            <Button variant="ghost" size="sm" onClick={handleLogout} data-testid="logout-btn">
              <LogOut className="w-4 h-4 mr-2" /> Logout
            </Button>
          </div>
        </div>
      </nav>

      <main className="max-w-4xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-2">
            <Badge className="bg-red-100 text-red-700 border-red-200">Ontario Requirements</Badge>
          </div>
          <h1 className="font-archivo font-bold text-3xl text-slate-900">Permits & Licenses</h1>
          <p className="text-slate-600 mt-1">
            Complete all required certifications to transport medical goods in Ontario
          </p>
        </div>

        {/* Progress Card */}
        <Card className="mb-8 border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="font-archivo font-bold text-xl text-slate-900">Compliance Progress</h2>
                <p className="text-slate-600 text-sm">
                  {completedCount} of {requiredPermits.length} required permits obtained
                </p>
              </div>
              <div className="text-right">
                <p className="font-archivo font-black text-4xl text-slate-900">{Math.round(progress)}%</p>
              </div>
            </div>
            <Progress value={progress} className="h-3" />
            {progress === 100 ? (
              <div className="mt-4 flex items-center gap-2 text-emerald-600">
                <CheckCircle className="w-5 h-5" />
                <span className="font-medium">All required permits obtained! You're ready to accept jobs.</span>
              </div>
            ) : (
              <div className="mt-4 flex items-center gap-2 text-amber-600">
                <AlertTriangle className="w-5 h-5" />
                <span className="font-medium">Complete all required permits to start accepting jobs.</span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Info Banner */}
        <Card className="mb-8 border-blue-200 bg-blue-50">
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              <Info className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-blue-800 text-sm">
                  <strong>Important:</strong> These permits and licenses are required by the Ontario Ministry 
                  of Transportation and Transport Canada for commercial medical transport operations. 
                  Click on each requirement for official information and application details.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Required Permits */}
        <div className="mb-8">
          <h2 className="font-archivo font-bold text-xl text-slate-900 mb-4 flex items-center gap-2">
            <Shield className="w-5 h-5 text-red-600" />
            Required Permits
          </h2>
          <div className="space-y-4">
            {requiredPermits.map((permit) => (
              <Card 
                key={permit.id} 
                className={`border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)] transition-all ${
                  driverPermits[permit.id] ? 'bg-emerald-50 border-l-4 border-l-emerald-500' : ''
                }`}
              >
                <CardContent className="p-6">
                  <div className="flex items-start gap-4">
                    <Checkbox
                      id={permit.id}
                      checked={driverPermits[permit.id] || false}
                      onCheckedChange={(checked) => handleTogglePermit(permit.id, checked)}
                      className="mt-1"
                      data-testid={`permit-${permit.id}-checkbox`}
                    />
                    <div className="flex-1">
                      <div className="flex items-start justify-between">
                        <div>
                          <h3 className="font-semibold text-slate-900 mb-1">{permit.name}</h3>
                          <p className="text-slate-600 text-sm mb-2">{permit.description}</p>
                          <p className="text-slate-500 text-xs">
                            Issued by: {permit.issuing_authority}
                          </p>
                        </div>
                        {driverPermits[permit.id] ? (
                          <Badge className="bg-emerald-100 text-emerald-700 flex-shrink-0">
                            <CheckCircle className="w-3 h-3 mr-1" /> Obtained
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="text-amber-600 border-amber-300 flex-shrink-0">
                            Pending
                          </Badge>
                        )}
                      </div>
                      <a
                        href={permit.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 text-sm font-medium mt-3"
                      >
                        <FileText className="w-4 h-4" />
                        View Official Information
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>

        {/* Optional Permits */}
        {optionalPermits.length > 0 && (
          <div>
            <h2 className="font-archivo font-bold text-xl text-slate-900 mb-4 flex items-center gap-2">
              <FileText className="w-5 h-5 text-slate-600" />
              Recommended Certifications
            </h2>
            <div className="space-y-4">
              {optionalPermits.map((permit) => (
                <Card 
                  key={permit.id} 
                  className={`border-0 shadow-sm ${
                    driverPermits[permit.id] ? 'bg-slate-50' : ''
                  }`}
                >
                  <CardContent className="p-6">
                    <div className="flex items-start gap-4">
                      <Checkbox
                        id={permit.id}
                        checked={driverPermits[permit.id] || false}
                        onCheckedChange={(checked) => handleTogglePermit(permit.id, checked)}
                        className="mt-1"
                        data-testid={`permit-${permit.id}-checkbox`}
                      />
                      <div className="flex-1">
                        <div className="flex items-start justify-between">
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <h3 className="font-semibold text-slate-900">{permit.name}</h3>
                              <Badge variant="outline" className="text-slate-500">Optional</Badge>
                            </div>
                            <p className="text-slate-600 text-sm mb-2">{permit.description}</p>
                            <p className="text-slate-500 text-xs">
                              Issued by: {permit.issuing_authority}
                            </p>
                          </div>
                          {driverPermits[permit.id] && (
                            <Badge className="bg-slate-100 text-slate-600 flex-shrink-0">
                              <CheckCircle className="w-3 h-3 mr-1" /> Obtained
                            </Badge>
                          )}
                        </div>
                        <a
                          href={permit.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 text-sm font-medium mt-3"
                        >
                          <FileText className="w-4 h-4" />
                          Learn More
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default PermitsPage;
