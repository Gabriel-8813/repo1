import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import StarRating from '../components/StarRating';
import { Truck, CheckCircle, MapPin, MessageSquare, ArrowRight } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const RatePage = () => {
  const { jobId } = useParams();
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState('');
  const [reviewerName, setReviewerName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    fetchInfo();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const fetchInfo = async () => {
    try {
      const r = await axios.get(`${API}/reviews/info/${jobId}`);
      setInfo(r.data);
    } catch (e) {
      setError(e.response?.data?.detail || 'Could not load trip');
    } finally {
      setLoading(false);
    }
  };

  const submit = async () => {
    if (rating === 0) {
      toast.error('Please select a rating');
      return;
    }
    setSubmitting(true);
    try {
      await axios.post(`${API}/reviews/${jobId}`, {
        rating,
        comment: comment || null,
        reviewer_name: reviewerName || null
      });
      setDone(true);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not submit review');
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center px-6">
        <Card className="max-w-md w-full">
          <CardContent className="p-8 text-center">
            <h1 className="font-archivo font-bold text-2xl text-slate-900 mb-2">Not Available</h1>
            <p className="text-slate-600 mb-6">{error}</p>
            <Link to="/"><Button variant="outline">Go to MediTrans</Button></Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (done || info.already_reviewed) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-amber-50 to-blue-50 flex items-center justify-center px-6">
        <Card className="max-w-md w-full shadow-xl border-0" data-testid="review-success-card">
          <CardContent className="p-10 text-center">
            <div className="w-20 h-20 rounded-full bg-emerald-100 flex items-center justify-center mx-auto mb-6">
              <CheckCircle className="w-10 h-10 text-emerald-600" />
            </div>
            <h1 className="font-archivo font-bold text-3xl text-slate-900 mb-3">
              {done ? 'Thanks for rating!' : 'Already rated'}
            </h1>
            <p className="text-slate-600 mb-6">
              {done
                ? `Your review helps ${info.driver.first_name} and future customers.`
                : 'This trip has already been reviewed.'}
            </p>
            <Link to="/"><Button variant="outline" className="rounded-full">
              Back to MediTrans <ArrowRight className="w-4 h-4 ml-2" />
            </Button></Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  const { trip, driver, driver_rating } = info;

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-slate-50 to-amber-50" data-testid="rate-page">
      <header className="py-6 px-6">
        <Link to="/" className="inline-flex items-center gap-2">
          <div className="w-9 h-9 bg-blue-600 rounded-lg flex items-center justify-center">
            <Truck className="w-5 h-5 text-white" />
          </div>
          <span className="font-archivo font-bold text-lg text-slate-900">MediTrans</span>
        </Link>
      </header>

      <main className="max-w-lg mx-auto px-6 pb-12">
        <div className="text-center mb-8">
          <h1 className="font-archivo font-bold text-3xl text-slate-900 mb-2">
            Rate {driver.first_name}
          </h1>
          <p className="text-slate-600">How was your medical transport experience?</p>
        </div>

        <Card className="mb-6 border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
          <CardContent className="p-5">
            <div className="flex items-start justify-between gap-3 mb-3">
              <h2 className="font-semibold text-slate-900">{trip.title}</h2>
              <Badge className="bg-emerald-100 text-emerald-700">Completed</Badge>
            </div>
            <div className="flex items-center gap-2 text-sm text-slate-600">
              <MapPin className="w-4 h-4 text-slate-400" />
              <span>{trip.pickup_city} → {trip.delivery_city}</span>
            </div>
            {driver_rating.count > 0 && (
              <p className="text-xs text-slate-500 mt-2">
                Current average: ★ {driver_rating.avg.toFixed(1)} ({driver_rating.count} reviews)
              </p>
            )}
          </CardContent>
        </Card>

        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
          <CardContent className="p-6">
            <div className="text-center mb-6">
              <Label className="text-slate-900 font-semibold block mb-4">Your rating</Label>
              <div className="flex justify-center">
                <StarRating value={rating} onChange={setRating} size="lg" testidPrefix="rate-star" />
              </div>
              {rating > 0 && (
                <p className="text-sm text-slate-500 mt-3">
                  {['', 'Terrible', 'Poor', 'OK', 'Good', 'Excellent'][rating]}
                </p>
              )}
            </div>

            <div className="space-y-4">
              <div>
                <Label htmlFor="comment" className="flex items-center gap-2">
                  <MessageSquare className="w-4 h-4" /> Comment (optional)
                </Label>
                <Textarea
                  id="comment"
                  placeholder="Share what went well or how they could improve"
                  value={comment}
                  onChange={e => setComment(e.target.value)}
                  rows={4}
                  maxLength={2000}
                  data-testid="rate-comment-input"
                />
              </div>
              <div>
                <Label htmlFor="name">Your name (optional)</Label>
                <Input
                  id="name"
                  placeholder="So they know who to thank"
                  value={reviewerName}
                  onChange={e => setReviewerName(e.target.value)}
                  data-testid="rate-name-input"
                  maxLength={80}
                />
              </div>
            </div>

            <Button
              onClick={submit}
              disabled={submitting || rating === 0}
              className="w-full rounded-full bg-blue-600 hover:bg-blue-700 text-white py-6 text-lg mt-6"
              data-testid="submit-review-btn"
            >
              {submitting ? 'Submitting...' : 'Submit Review'}
            </Button>

            <p className="text-xs text-slate-500 text-center mt-4">
              Your review will be visible publicly. One review per trip.
            </p>
          </CardContent>
        </Card>
      </main>
    </div>
  );
};

export default RatePage;
