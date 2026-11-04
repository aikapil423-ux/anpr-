import unittest

from src.pipeline.video_sampling import VideoFrameSampler


class VideoSamplingTests(unittest.TestCase):
    def test_selected_rate_for_ten_seconds(self):
        for source in (25, 30, 60):
            for requested in (5, 10, 20):
                with self.subTest(source=source, requested=requested):
                    sampler = VideoFrameSampler(source, requested)
                    selected = [i for i in range(1, source * 10 + 1) if sampler.includes(i)]
                    self.assertEqual(len(selected), requested * 10)
                    self.assertEqual(sampler.count(source * 10), len(selected))

    def test_all_frames_and_source_limit(self):
        for requested in (0, 20):
            sampler = VideoFrameSampler(15, requested)
            self.assertEqual(sampler.output_fps, 15)
            self.assertTrue(all(sampler.includes(i) for i in range(1, 151)))

    def test_no_forced_extra_last_frame(self):
        sampler = VideoFrameSampler(25, 5)
        self.assertEqual([i for i in range(1, 26) if sampler.includes(i)], [1, 6, 11, 16, 21])

    def test_fractional_source_and_short_clips(self):
        sampler = VideoFrameSampler(29.97, 10)
        for total in (0, 1, 2, 17, 300):
            self.assertEqual(sampler.count(total), sum(sampler.includes(i) for i in range(1, total + 1)))


if __name__ == '__main__':
    unittest.main()
